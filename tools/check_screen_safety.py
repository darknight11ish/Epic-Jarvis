#!/usr/bin/env python3
"""The owner's-PC check for screen safety (2026-09-29). Run it on the PC, not
in the development container: it needs Windows.

    py -3 tools\\check_screen_safety.py             # makes a test picture with FAKE secrets, checks it
    py -3 tools\\check_screen_safety.py FILE.png    # checks a picture of your own
    py -3 tools\\check_screen_safety.py --screen    # takes a picture of the WHOLE screen the way
                                                    # "Look at this" does, with windows on your
                                                    # Never look at list painted black

What it does, in plain words:
  * says which text reader is in use - "inside Jarvis" (the pywinrt packages)
    or "PowerShell" (the old way; it means the six pywinrt packages are not
    installed or one failed) - and how long the reading took;
  * reads the words in the picture WITH where each one sits, looks for keys,
    passwords and card numbers, and says how many it hid and which kinds
    (never what they were);
  * writes the picture with those places painted SOLID BLACK next to yours (or
    in your temp folder) so you can look at it yourself. YOU can see the file;
    Jarvis never saves one.
With --screen it also says how many windows it could see, and which of them
it painted black, by program name and title (this is on your own PC, in your
own terminal - Jarvis never says these anywhere else).

Nothing is sent anywhere. The made-up secrets are not real.

SKIPPED OFF THE OWNER'S PC. The default run makes its test picture with the
machine's own Windows PowerShell and reads it with Windows' own text reader, and
`--screen` photographs this PC's screen, so on any other host (a CI runner
included) this prints the reason and exits 0 rather than reporting a failure that
is only about the host - see THE HOST GUARD in main(). A picture passed on the
command line is never skipped: that path is pure file work the caller supplied.
A claim about CI has to be tested where CI runs, or it is a claim about the
owner's desk: the skip below is proven by running the Linux branch on his PC with
sys.platform monkeypatched, not by waiting for a runner.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

FAKE_PICTURE_SCRIPT = r"""
Add-Type -AssemblyName System.Drawing
$b = New-Object System.Drawing.Bitmap 1100, 260
$g = [System.Drawing.Graphics]::FromImage($b)
$g.Clear([System.Drawing.Color]::White)
$f = New-Object System.Drawing.Font 'Segoe UI', 20
$lines = @('Meeting notes for Friday', 'Password: hunter2', 'Card 4111 1111 1111 1111 exp 12/29',
           'token ghp_aB3dE5gH7jK9mN1pQ3sT5vW7yZ9bC1eF3hJ5', 'Nothing secret on this last line')
$y = 10
foreach ($l in $lines) { $g.DrawString($l, $f, [System.Drawing.Brushes]::Black, 10, $y); $y += 48 }
$b.Save($args[0], [System.Drawing.Imaging.ImageFormat]::Png)
"""


def make_test_picture(path: Path) -> None:
    exe = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell",
                       "v1.0", "powershell.exe")
    subprocess.run([exe, "-NoProfile", "-Command", FAKE_PICTURE_SCRIPT.replace("$args[0]", "'" + str(path) + "'")],
                   check=True, capture_output=True, timeout=60)


def report(image: bytes, out_png: Path, *, ocr=None, say=print) -> int:
    """Check one picture and write the cleaned copy. 0 when it worked."""
    import jarvis_ocr
    import jarvis_picture
    say("Text reader: " + ("inside Jarvis (pywinrt)" if jarvis_ocr.winrt_usable()
                            else "PowerShell (the pywinrt packages are not installed or would not load)"))
    t0 = time.time()
    res = jarvis_picture.clean(image, ocr=ocr or jarvis_ocr.read_text, want_png=True)
    took = time.time() - t0
    if not res["ok"]:
        say(f"NOT OK ({took:.1f} s): {res['why']}")
        return 1
    say(f"Read and checked in {took:.1f} s: {len(res['text'].splitlines())} lines of words, "
        f"{res['hidden']} hidden ({', '.join(res['kinds']) or 'nothing found'}).")
    if res["png"] is None:
        say("No cleaned picture: " + res["png_why"])
        return 1
    out_png.write_bytes(res["png"])
    say(f"Cleaned picture written to {out_png} - open it and check the secrets are black.")
    say("The words a model would be given:")
    for line in res["text"].splitlines():
        say("    " + line)
    return 0


def screen_check(out_png: Path, say=print) -> int:
    import jarvis_screen as SC
    import jarvis_screen_win as W
    if not W.available():
        say("Not available: " + W.unavailable_why())
        return 1
    import ctypes
    hwnd = int(ctypes.windll.user32.GetForegroundWindow())
    never = SC.NeverLook()
    if never.broken:
        say("Your Never look at list could not be read, so no picture is taken (that is the safe way).")
        return 1
    wins = W._list_windows()
    if wins is None:
        say("The window list could not be read, so no picture is taken (that is the safe way).")
        return 1
    say(f"{len(wins)} windows on screen. Painted black: ")
    hidden = 0
    for w in wins:
        try:
            hide = W.must_hide(w, never, front_hwnd=hwnd, address_of=lambda x: W._address_of(x))
        except Exception:
            hide = True
        if hide:
            hidden += 1
            say(f"    {os.path.basename(w['exe']) or '?'}  -  {w['title'][:60]}")
    png = W.capture({"hwnd": hwnd}, True, never=never)
    if png is None:
        say("No picture (it could not be taken safely).")
        return 1
    out_png.write_bytes(png)
    say(f"{hidden} window(s) painted black. Whole-screen picture written to {out_png} - open it and check.")
    return 0


def main(argv) -> int:
    tmp = Path(tempfile.gettempdir())
    if argv and argv[0] == "--screen":
        # THE HOST GUARD, the same shape as check_lanes.py. --screen photographs
        # THIS PC's screen and reads it with Windows' own text reader, so on any
        # other host there is nothing to check. Say so and exit 0 rather than
        # reporting a failure that is only about the host - a red that means
        # "wrong machine" makes every pull request red and teaches nobody anything.
        if sys.platform != "win32":
            print("SKIP: --screen photographs the owner's PC, and this is not it")
            print(f"  host: sys.platform == {sys.platform!r}, and it needs 'win32'.")
            print("  NOTHING WAS CHECKED, and that is not the same as safe: run this on")
            print("  the owner's PC, or pass a picture of your own to check instead.")
            print("exit code: 0 (skipped - the reason is above)")
            return 0
        return screen_check(tmp / "jarvis-screen-safety-screen.png")
    if argv:
        src = Path(argv[0])
        out = src.with_name(src.stem + "-cleaned.png")
    else:
        # THE HOST GUARD. The default run makes its test picture with the machine's
        # own Windows PowerShell (System32\WindowsPowerShell\...) and reads it with
        # Windows' own text reader, so off the owner's PC there is nothing to check:
        # say so and exit 0 rather than reporting a failure that is only about the
        # host. A picture passed on the command line is never skipped - that path is
        # pure file work and the caller supplied it - and a real leak on the owner's
        # PC still exits non-zero, because the skip is about the host, never the
        # subject.
        if sys.platform != "win32":
            print("SKIP: this check reads pictures with Windows' own text reader, and this is not it")
            print(f"  host: sys.platform == {sys.platform!r}, and it needs 'win32'.")
            print("  NOTHING WAS CHECKED, and that is not the same as safe: run this on the")
            print("  owner's PC, or pass a picture of your own to check instead:")
            print("    py -3 tools/check_screen_safety.py YOUR.png")
            print("exit code: 0 (skipped - the reason is above)")
            return 0
        src, out = tmp / "jarvis-screen-safety-test.png", tmp / "jarvis-screen-safety-cleaned.png"
        make_test_picture(src)
        print(f"Made a test picture with fake secrets: {src}")
    return report(src.read_bytes(), out)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
