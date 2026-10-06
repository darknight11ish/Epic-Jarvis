"""test_screen_win.py - the Windows readers of "Look at this" / "Watch with me"
(jarvis_screen_win.py), the parts that run on any machine.

    python3 backend/test_screen_win.py

What it proves:
  - a picture's raw pixels become a real PNG in memory (read back here with a
    small decoder, pixel for pixel), and the half-size fallback is a real,
    smaller PNG of the same picture;
  - the lock rule: "Default" desktop is not locked, access denied is locked,
    "Winlogon" (a UAC prompt) is a pause and not a lock, and a failure is
    "cannot tell";
  - the rectangle clipping: a window half off the screen is cut to what is on
    it, and one wholly off screen (or a sliver) is nothing;
  - the window-text walk: labels and text boxes are read, a password box is
    marked and neither its label nor its value nor anything inside it appears
    anywhere, a control that raises is treated as a password box, and both
    budgets (nodes and time) stop it;
  - the readers are built from what jarvis_screen expects;
  - nothing here writes a file or opens a socket.
The ctypes and UI Automation calls need Windows and are not run here: see the
module's own header for what that leaves unverified.
"""
from __future__ import annotations

import os
import socket
import struct
import sys
import traceback
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import SHIPPED, require_shipped  # noqa: E402

require_shipped("jarvis_screen_win.py", "jarvis_front.py")

import jarvis_screen_win as W  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def decode_png(png: bytes):
    """(width, height, RGB bytes) - filter type 0 only, which is all we write."""
    assert png[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    pos, idat, w, h = 8, b"", 0, 0
    while pos < len(png):
        (n,) = struct.unpack(">I", png[pos:pos + 4])
        kind, data = png[pos + 4:pos + 8], png[pos + 8:pos + 8 + n]
        (crc,) = struct.unpack(">I", png[pos + 8 + n:pos + 12 + n])
        assert crc == zlib.crc32(kind + data) & 0xFFFFFFFF, "bad chunk checksum"
        if kind == b"IHDR":
            w, h, depth, ctype = struct.unpack(">IIBB", data[:10])
            assert (depth, ctype) == (8, 2)
        elif kind == b"IDAT":
            idat += data
        pos += 12 + n
    raw = zlib.decompress(idat)
    stride = w * 3
    rows = []
    for y in range(h):
        o = y * (stride + 1)
        assert raw[o] == 0
        rows.append(raw[o + 1:o + 1 + stride])
    return w, h, b"".join(rows)


def bgra_of(w, h, pixel):
    out = bytearray()
    for y in range(h):
        for x in range(w):
            r, g, b = pixel(x, y)
            out += bytes((b, g, r, 255))
    return bytes(out)


def t_png():
    w, h = 37, 21
    px = lambda x, y: ((x * 7) % 256, (y * 11) % 256, (x + y) % 256)   # noqa: E731
    png = W.png_from_bgra(bgra_of(w, h, px), w, h)
    dw, dh, rgb = decode_png(png)
    want = b"".join(bytes(px(x, y)) for y in range(h) for x in range(w))
    check("a PNG is made from raw pixels, in memory, pixel for pixel",
          (dw, dh) == (w, h) and rgb == want)
    try:
        W.png_from_bgra(b"\0" * 8, 10, 10)
        bad = False
    except ValueError:
        bad = True
    check("pixels that do not match the size are refused, not guessed", bad)

    w, h = 64, 48
    px2 = lambda x, y: (200 if (x // 4 + y // 4) % 2 else 20, 90, 30)   # noqa: E731
    big = W.png_from_bgra(bgra_of(w, h, px2), w, h)
    half = W.png_half_size(bgra_of(w, h, px2), w, h)
    hw, hh, hrgb = decode_png(half)
    check("the half-size fallback is a real PNG of half the width and height",
          (hw, hh) == (32, 24) and len(hrgb) == 32 * 24 * 3)
    ok = all(hrgb[(y * 32 + x) * 3:(y * 32 + x) * 3 + 3] == bytes(px2(x * 2, y * 2))
             for y in range(24) for x in range(32))
    check("... made of every second pixel of every second row", ok)
    check("... and the half-size one is smaller", len(half) < len(big) * 2)
    odd = W.png_half_size(bgra_of(9, 7, px), 9, 7)
    check("an odd size still halves (rounding down)", decode_png(odd)[:2] == (4, 3))


def t_lock_rule():
    check("Default desktop = someone is working = not locked",
          W.locked_from_desktop("Default", False) is False
          and W.locked_from_desktop("default", False) is False)
    check("refused the input desktop = the lock screen", W.locked_from_desktop(None, True) is True)
    check("Winlogon (a UAC prompt) is 'cannot tell', which pauses - never a lock",
          W.locked_from_desktop("Winlogon", False) is None)
    check("a screen saver is not a lock by itself",
          W.locked_from_desktop("Screen-saver", False) is None)
    check("a failure is 'cannot tell'", W.locked_from_desktop(None, False) is None)


def t_rect():
    screen = (0, 0, 1920, 1080)
    check("a window on screen is kept whole",
          W.clip_rect((100, 100, 900, 700), screen) == (100, 100, 900, 700))
    check("a window half off the screen is cut to what is on it",
          W.clip_rect((-200, 50, 400, 500), screen) == (0, 50, 400, 500))
    check("a window wholly off screen is nothing", W.clip_rect((2000, 0, 2400, 300), screen) is None)
    check("a sliver is nothing", W.clip_rect((0, 0, 4, 500), screen) is None)
    check("a second monitor to the left works (negative left)",
          W.clip_rect((-1800, 0, -900, 600), (-1920, 0, 1920, 1080)) == (-1800, 0, -900, 600))


class Node:
    def __init__(self, kind="TextControl", name="", value="", password=False, kids=(), boom=False):
        self.kind, self.name, self.value, self.password = kind, name, value, password
        self.kids, self.boom = list(kids), boom


def kids_of(n):
    return n.kids


def describe(n):
    if n.boom:
        raise RuntimeError("cannot ask")
    return {"type": n.kind, "name": n.name, "value": n.value, "password": n.password}


def t_walk():
    tree = Node("WindowControl", "Bank", kids=[
        Node("TextControl", "Sign in to Zqxwarblefonk"),
        Node("EditControl", "User name", value="alice-plimberton"),
        Node("GroupControl", "", kids=[
            Node("EditControl", "Password", value="hunter2-vlorpt", password=True,
                 kids=[Node("TextControl", "hunter2-inside")]),
            Node("ButtonControl", "Sign in"),
        ]),
    ])
    got = W.walk_words(tree, kids_of, describe)
    words = [g["text"] for g in got if g["text"]]
    check("labels and text boxes are read (a text box gives its value)",
          "Sign in to Zqxwarblefonk" in words and "alice-plimberton" in words
          and "Sign in" in words, words)
    blob = repr(got)
    check("a password box's label, value and everything inside it are NOT there",
          not any(x in blob for x in ("hunter2", "Password")), blob)
    check("... it is marked, so jarvis_screen skips it a second time", any(g["password"] for g in got))

    flaky = Node("WindowControl", "w", kids=[Node("EditControl", "x", boom=True),
                                             Node("TextControl", "fine")])
    got = W.walk_words(flaky, kids_of, describe)
    check("a control that cannot be asked is treated as a password box",
          [g["text"] for g in got if g["text"]] == ["fine"] and any(g["password"] for g in got))

    many = Node("WindowControl", "w", kids=[Node("TextControl", f"line {i}") for i in range(2000)])
    got = W.walk_words(many, kids_of, describe, budget=50)
    check("the node budget stops the walk", len(got) <= 50, len(got))

    t = [0.0]

    def clock():
        t[0] += 1.0
        return t[0]
    got = W.walk_words(many, kids_of, describe, seconds=5.0, clock=clock)
    check("the time budget stops the walk", len(got) < 20, len(got))

    dup = Node("WindowControl", "w", kids=[Node("TextControl", "same"), Node("TextControl", "same")])
    check("the same words are not listed twice in a row",
          [g["text"] for g in W.walk_words(dup, kids_of, describe)] == ["same"])


def t_built():
    r = W.readers()
    check("the three readers jarvis_screen.Screen is built from",
          set(r) == {"front_reader", "capture", "ui_text"} and all(callable(v) for v in r.values()))
    # `available()` is Windows AND the `uiautomation` package, so this suite is
    # meaningful both ways: on the owner's PC it proves the readers really are
    # there, and on CI (Linux) that they are absent and say why. It used to
    # assert the off-Windows answer on every machine, so it could only ever pass
    # off Windows (2026-10-03).
    if os.name == "nt":
        check("on Windows the screen readers are available",
              W.available() is True and W.unavailable_why() == "", W.unavailable_why())
    else:
        check("off Windows nothing is available, and it says why",
              W.available() is False and "not Windows" in W.unavailable_why())
    check("off Windows the capture and the text reader give nothing, quietly",
          W.capture({"hwnd": 5}, False) is None and W.ui_text({"hwnd": 5}) == [])


def t_hygiene():
    src = (HERE / "jarvis_screen_win.py").read_text(encoding="utf-8")
    check("no socket, no file written, no subprocess in the readers",
          not any(x in src for x in ("socket", "open(", "write_text", "write_bytes", "subprocess",
                                      "urllib", "requests", "tempfile")))
    check("shipped (apply-patches.ps1 $SHIPPED and _where.SHIPPED)",
          "jarvis_screen_win.py" in SHIPPED
          and "jarvis_screen_win.py" in (HERE.parent / "scripts" / "apply-patches.ps1")
          .read_text(encoding="utf-8"))


def main():
    real = socket.socket.connect
    socket.socket.connect = lambda *a, **k: (_ for _ in ()).throw(AssertionError("no network here"))
    try:
        for fn in (t_png, t_lock_rule, t_rect, t_walk, t_built, t_hygiene):
            try:
                fn()
            except Exception:
                FAILED.append(fn.__name__)
                print("FAIL " + fn.__name__)
                traceback.print_exc()
    finally:
        socket.socket.connect = real
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
