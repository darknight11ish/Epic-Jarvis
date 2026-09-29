"""test_screen_masks.py - painting the windows Jarvis must not show black
(jarvis_screen_win.py: must_hide, mask_rects, take_picture) and the safer
window-text walk.

    python3 backend/test_screen_masks.py

What it proves (screen safety, part 3, 2026-09-29). All of it is geometry and
rules over made-up window lists - the Windows calls that FILL a list are not
run here (see jarvis_screen_win.py's header):
  - subtract_rects: what is left of a rectangle after windows in front of it
    are cut out (checked pixel by pixel on random cases);
  - a window on the Never look at list that is visible in the picture is
    painted over - even when it is not the one in front - grown a little so
    no edge shows, and clipped to the picture;
  - one hidden entirely behind an opaque window is NOT painted (the picture
    would lose part of what is in front for nothing), and Jarvis does not
    waste time reading its address box;
  - a see-through or click-through window is never counted as hiding what is
    behind it (it could be an invisible overlay);
  - a private browser window, one of Jarvis's own windows, the lock screen
    and admin prompts are painted over too;
  - a browser window that is not in front: a listed site is painted over, an
    allowed one is not, one whose site cannot be read (or after too many have
    been asked about) is painted over;
  - take_picture fails closed: no list, an unreadable list, a window list
    that cannot be had before or after the grab, a grab that fails, or
    anything raising gives NO picture; and with everything working the
    black really is in the PNG;
  - the window-text walk skips off-screen controls (and what is inside them),
    reads what is on screen, treats "cannot tell" as off screen, and has a
    quarter-second budget.
"""
from __future__ import annotations

import random
import sys
import tempfile
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_screen_win.py", "jarvis_screen.py", "jarvis_front.py", "jarvis_picture.py",
                "jarvis_secrets.py", "jarvis_secret_rules.py", "jarvis_stop_all.py")

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-masks-"))
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _TMP
fw.LOG_DIR = _TMP
fw.load_framework = lambda: {}
fw.audit_log = lambda event, detail=None, **k: None
fw.action_tier = lambda action: "ask"
sys.modules["jarvis_framework"] = fw

import jarvis_screen as SC  # noqa: E402
import jarvis_screen_win as W  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def never_list():
    return SC.NeverLook(Path(tempfile.mkdtemp(prefix="jarvis-never-")) / "n.json")


CAP = (0, 0, 1000, 600)          # the capture rectangle (screen pixels)


def win(hwnd, exe, rect, title="", opaque=True):
    return {"hwnd": hwnd, "exe": rf"C:\Apps\{exe}", "title": title, "rect": rect, "opaque": opaque}


def area(rects):
    seen = set()
    for l, t, r, b in rects:
        for x in range(int(l), int(r)):
            for y in range(int(t), int(b)):
                seen.add((x, y))
    return seen


def covers(rects, x, y):
    return any(l <= x < r and t <= y < b for l, t, r, b in rects)


def t_subtract():
    check("nothing cut: the whole rectangle", W.subtract_rects((0, 0, 10, 10), []) == [(0, 0, 10, 10)])
    check("fully covered: nothing left", W.subtract_rects((2, 2, 8, 8), [(0, 0, 10, 10)]) == [])
    check("a cutter that does not touch it changes nothing",
          W.subtract_rects((0, 0, 10, 10), [(20, 20, 30, 30)]) == [(0, 0, 10, 10)])
    rng = random.Random(7)
    ok = True
    for _ in range(300):
        rect = (rng.randint(0, 20), rng.randint(0, 20), rng.randint(21, 40), rng.randint(21, 40))
        cuts = [(rng.randint(0, 40), rng.randint(0, 40), rng.randint(0, 45), rng.randint(0, 45))
                for _ in range(rng.randint(0, 4))]
        cuts = [(min(a, c), min(b, d), max(a, c), max(b, d)) for a, b, c, d in cuts]
        pieces = W.subtract_rects(rect, cuts)
        want = {(x, y) for x in range(rect[0], rect[2]) for y in range(rect[1], rect[3])
                if not any(c[0] <= x < c[2] and c[1] <= y < c[3] for c in cuts)}
        pts = [(x, y) for p in pieces for x in range(p[0], p[2]) for y in range(p[1], p[3])]
        ok = ok and set(pts) == want and len(pts) == len(want)         # right area, no overlaps
    check("300 random cases: exactly what is left, each pixel once", ok)


def t_masks():
    never = never_list()
    chrome = win(1, "chrome.exe", (0, 0, 1000, 600), "Docs - Google Chrome")
    keepass = win(2, "KeePass.exe", (700, 100, 900, 300), "Passwords")
    asked = []

    def address(w):
        asked.append(w["hwnd"])
        return "example.com"

    # 1. KeePass beside the front window: painted over, grown, clipped
    small_front = win(1, "chrome.exe", (0, 0, 600, 600), "Docs - Google Chrome")
    got = W.mask_rects([small_front, keepass], capture_rect=CAP, never=never, front_hwnd=1,
                       address_of=address)
    check("a Never look at program beside the front window is painted over",
          len(got) == 1 and got[0][0] <= 700 and got[0][2] >= 900 and got[0][1] <= 100
          and got[0][3] >= 300, str(got))
    check("... grown by the margin so no edge shows",
          got[0] == (700 - W.MASK_MARGIN, 100 - W.MASK_MARGIN, 900 + W.MASK_MARGIN, 300 + W.MASK_MARGIN))
    # 2. behind an opaque front window: nothing to paint, and no address asked
    got = W.mask_rects([chrome, keepass], capture_rect=CAP, never=never, front_hwnd=1, address_of=address)
    check("hidden entirely behind an opaque window: NOT painted", got == [], str(got))
    # 3. behind a see-through window: still painted (it could be an invisible overlay)
    ghost = win(9, "overlay.exe", (0, 0, 1000, 600), "", opaque=False)
    got = W.mask_rects([ghost, keepass], capture_rect=CAP, never=never, front_hwnd=1, address_of=address)
    check("a see-through or click-through window never counts as hiding what is behind it: "
          "a listed program behind only a ghost is painted", len(got) == 1 and covers(got, 800, 200))
    # 4. partly covered: only the visible part
    half = win(3, "notepad.exe", (0, 0, 800, 600), "notes")
    got = W.mask_rects([half, keepass], capture_rect=CAP, never=never, front_hwnd=3, address_of=address)
    check("partly covered: only the part in view is painted",
          covers(got, 850, 200) and not covers(got, 750, 200) and not covers(got, 600, 200), str(got))
    check("... and never more than the window plus the margin",
          all(700 - W.MASK_MARGIN <= l and r <= 900 + W.MASK_MARGIN for l, t, r, b in got))
    # 5. clipped to the picture
    edge = win(4, "KeePassXC.exe", (900, 500, 1200, 800), "")
    got = W.mask_rects([edge], capture_rect=CAP, never=never, front_hwnd=1, address_of=address)
    check("a listed window half outside the picture is clipped to it",
          len(got) == 1 and got[0][2] == CAP[2] and got[0][3] == CAP[3], str(got))
    off = win(5, "KeePass.exe", (2000, 2000, 2400, 2400), "")
    check("one wholly outside the picture is nothing",
          W.mask_rects([off], capture_rect=CAP, never=never, front_hwnd=1, address_of=address) == [])
    # 6. things that are hidden whoever asks
    for exe, title, why in (("jarvis-desktop.exe", "Jarvis", "one of Jarvis's own windows"),
                            ("something.exe", "Jarvis Bar", "a window titled as Jarvis's"),
                            ("LockApp.exe", "", "the lock screen"),
                            ("consent.exe", "User Account Control", "an admin prompt"),
                            ("CredentialUIBroker.exe", "", "the Windows sign-in prompt")):
        got = W.mask_rects([win(6, exe, (100, 100, 300, 300), title)], capture_rect=CAP, never=never,
                           front_hwnd=1, address_of=address)
        check("painted over: " + why, len(got) == 1, str(got))
    for exe, title in (("msedge.exe", "New tab - [InPrivate] - Microsoft Edge"),
                       ("chrome.exe", "Incognito - Google Chrome"),
                       ("firefox.exe", "Mozilla Firefox Private Browsing")):
        got = W.mask_rects([win(7, exe, (100, 100, 300, 300), title)], capture_rect=CAP, never=never,
                           front_hwnd=1, address_of=address)
        check("painted over: a private window (" + title[:24] + ")", len(got) == 1)
    got = W.mask_rects([win(8, "winword.exe", (100, 100, 300, 300), "Incognito notes.docx")],
                       capture_rect=CAP, never=never, front_hwnd=1, address_of=address)
    check("a non-browser with that word in its title is left alone", got == [])
    got = W.mask_rects([win(8, "", (100, 100, 300, 300), "")], capture_rect=CAP, never=never,
                       front_hwnd=1, address_of=address)
    check("a window whose program cannot be told is left alone (nothing to compare)", got == [])
    # 7. owner's own entry
    never.add("program", "MyBank.exe")
    got = W.mask_rects([win(10, "MyBank.exe", (10, 10, 100, 100), "")], capture_rect=CAP, never=never,
                       front_hwnd=1, address_of=address)
    check("the owner's own entry is painted over", len(got) == 1)


def t_browsers():
    never = never_list()
    never.add("site", "mybank.example")
    sites = {21: "mybank.example", 22: "docs.example.org", 23: "", 24: "www.netflix.com"}
    asked = []

    def address(w):
        asked.append(w["hwnd"])
        v = sites[w["hwnd"]]
        if v == "boom":
            raise RuntimeError("uia")
        return v

    def b(h, rect):
        return win(h, "chrome.exe", rect, "Page - Google Chrome")

    front = b(20, (0, 0, 400, 600))
    def masked(h, rect):
        return W.mask_rects([front, b(h, rect)], capture_rect=CAP, never=never, front_hwnd=20,
                            address_of=address)
    check("a browser window beside the front one, on a listed site: painted over",
          len(masked(21, (500, 0, 900, 600))) == 1)
    check("... on an allowed site: left alone", masked(22, (500, 0, 900, 600)) == [])
    check("... whose site cannot be read (\"\"): painted over - the same 'cannot tell' rule as a pause",
          len(masked(23, (500, 0, 900, 600))) == 1)
    check("... on a built-in streaming site: painted over", len(masked(24, (500, 0, 900, 600))) == 1)
    sites[25] = "boom"
    check("... when reading its address box raises: painted over", len(masked(25, (500, 0, 900, 600))) == 1)
    asked.clear()
    W.mask_rects([front], capture_rect=CAP, never=never, front_hwnd=20, address_of=address)
    check("the FRONT browser window is not asked about (the pause rules already checked it)", asked == [])
    asked.clear()
    W.mask_rects([b(21, (0, 0, 1000, 600)), b(22, (100, 100, 200, 200))], capture_rect=CAP, never=never,
                 front_hwnd=21, address_of=address)
    check("a browser window entirely hidden behind an opaque one is never asked about", asked == [])
    many = [win(30 + i, "chrome.exe", (500 + i * 20, 0, 500 + i * 20 + 8, 600), "x - Google Chrome")
            for i in range(W.ADDRESS_MAX_WINDOWS + 3)]
    for i in range(len(many)):
        sites[30 + i] = "docs.example.org"
    asked.clear()
    got = W.mask_rects([front] + many, capture_rect=CAP, never=never, front_hwnd=20, address_of=address)
    check("only a few address boxes are read per picture; the rest are painted over (cannot tell)",
          len(asked) == W.ADDRESS_MAX_WINDOWS and len(got) == 3, f"{len(asked)} asked, {len(got)} painted")


def t_pieces():
    never = never_list()
    keep = win(1, "KeePass.exe", (0, 0, 1000, 600), "")
    covers_ = [win(10 + i, "a.exe", (i * 30, i * 30, i * 30 + 20, i * 30 + 20), "") for i in range(30)]
    old = W.MASK_MAX_PIECES
    W.MASK_MAX_PIECES = 8
    try:
        got = W.mask_rects(covers_ + [keep], capture_rect=CAP, never=never, front_hwnd=99, address_of=None)
    finally:
        W.MASK_MAX_PIECES = old
    check("a window cut into too many pieces is painted whole (a safe over-cover)",
          len(got) == 1 and got[0][0] <= 0 and got[0][2] >= 1000, str(got[:2]))
    check("local_boxes moves screen rectangles into the picture's own pixels",
          W.local_boxes([(110, 220, 150, 260)], (100, 200, 500, 500)) == [(10, 20, 50, 60)])


# ---------------------------------------------------------------- take_picture

def solid(w, h, colour=(200, 200, 200)):
    return bytes(bytes((colour[2], colour[1], colour[0], 255)) * (w * h)), w, h


def decode(png):
    import jarvis_picture as P
    return P.decode_png(png)


def t_take():
    never = never_list()
    snap = {"hwnd": 1}
    w, h = 100, 60
    rect = (10, 20, 110, 80)
    keep = win(2, "KeePass.exe", (60, 30, 90, 50), "")
    front = win(1, "chrome.exe", rect, "x")
    calls = []

    def kit(**over):
        base = {"rect_of": lambda hw, whole: rect, "grab": lambda r: solid(w, h),
                "list_windows": lambda: [keep, front], "address_of": lambda w_: "example.com"}
        base.update(over)
        return base

    png = W.take_picture(snap, False, never, **kit())
    dec = decode(png) if png else None
    check("with everything working, a PNG comes back", dec is not None and dec[1:] == (w, h))
    px = lambda x, y: bytes(dec[0][(y * w + x) * 4:(y * w + x) * 4 + 4])   # noqa: E731
    # KeePass is at screen (60..90, 30..50) -> picture (50..80, 10..30)
    check("... with the listed window's place SOLID BLACK", px(65, 20) == b"\x00\x00\x00\xff"
          and px(50, 10) == b"\x00\x00\x00\xff" and px(79, 29) == b"\x00\x00\x00\xff")
    check("... and everything well away from it untouched",
          px(5, 5) == b"\xc8\xc8\xc8\xff" and px(95, 55) == b"\xc8\xc8\xc8\xff")
    # a window in the list only AFTER the grab (it opened while the grab ran) is covered too
    seq = [[front], [keep, front]]
    png = W.take_picture(snap, False, never, **kit(list_windows=lambda: seq.pop(0)))
    dec = decode(png)
    check("a window that appeared while the picture was being taken is covered (the list is read after too)",
          bytes(dec[0][(20 * w + 65) * 4:(20 * w + 65) * 4 + 4]) == b"\x00\x00\x00\xff")
    seq = [[keep, front], [front]]
    png = W.take_picture(snap, False, never, **kit(list_windows=lambda: seq.pop(0)))
    dec = decode(png)
    check("... and one that closed while it was being taken is covered too (the list is read before)",
          bytes(dec[0][(20 * w + 65) * 4:(20 * w + 65) * 4 + 4]) == b"\x00\x00\x00\xff")
    png = W.take_picture(snap, False, never, **kit(list_windows=lambda: [front]))
    dec = decode(png)
    check("nothing to hide: the picture is as it was", bytes(dec[0]) == solid(w, h)[0])
    # fail closed
    check("no Never look at list: NO picture", W.take_picture(snap, False, None, **kit()) is None)
    broken = never_list()
    broken.broken = True
    check("a list that could not be read: NO picture", W.take_picture(snap, False, broken, **kit()) is None)
    check("the window list cannot be read BEFORE the grab: NO picture",
          W.take_picture(snap, False, never, **kit(list_windows=lambda: None)) is None)
    seq = [[front], None]
    check("... or AFTER it: NO picture",
          W.take_picture(snap, False, never, **kit(list_windows=lambda: seq.pop(0))) is None)
    check("the grab fails: NO picture", W.take_picture(snap, False, never, **kit(grab=lambda r: None)) is None)
    check("no rectangle (a minimised window): NO picture",
          W.take_picture(snap, False, never, **kit(rect_of=lambda hw, whole: None)) is None)
    check("a window list that raises: NO picture, quietly",
          W.take_picture(snap, False, never, **kit(list_windows=lambda: 1 / 0)) is None)
    calls.clear()

    def bad_addr(w_):
        raise RuntimeError("x")
    bwin = win(3, "chrome.exe", (60, 30, 90, 50), "Bank - Google Chrome")
    png = W.take_picture(snap, False, never, **kit(list_windows=lambda: [bwin, front], address_of=bad_addr))
    check("an address box that raises is covered, not fatal", png is not None
          and bytes(decode(png)[0][(20 * w + 65) * 4:(20 * w + 65) * 4 + 4]) == b"\x00\x00\x00\xff")
    # reads the list once before and once after
    n = []
    W.take_picture(snap, False, never, **kit(list_windows=lambda: (n.append(1), [front])[1]))
    check("the window list is read twice: just before and just after the grab", len(n) == 2)
    import inspect
    src = inspect.getsource(W.capture)
    check("the real capture will not run without the list, and hands everything to take_picture",
          "never is None or getattr(never, \"broken\", True)" in src and "take_picture(" in src)
    check("off Windows, capture and the window list give nothing",
          W.capture({"hwnd": 5}, False, never) is None)
    r = W.readers(never=lambda: never)
    check("the readers pass the list through, and a reader without one takes no picture",
          set(r) == {"front_reader", "capture", "ui_text"} and r["capture"]({"hwnd": 5}, False) is None
          and W.readers()["capture"]({"hwnd": 5}, False) is None)


# ---------------------------------------------------------------- the text walk

class N:
    def __init__(self, name, kids=(), **kw):
        self.name, self.kids, self.kw = name, list(kids), kw


def t_walk():
    def describe(n):
        d = {"type": n.kw.get("type", "TextControl"), "name": n.name, "value": n.kw.get("value", ""),
             "password": n.kw.get("password", False)}
        if "offscreen" in n.kw:
            d["offscreen"] = n.kw["offscreen"]
        return d
    visited = []

    def kids_of(n):
        visited.append(n.name)
        return n.kids

    tree = N("root", [N("visible one"), N("scrolled away", [N("inside hidden")], offscreen=True),
                      N("visible two", [N("visible child")], offscreen=False),
                      N("unsure", [N("inside unsure")], offscreen=None)])
    got = [g["text"] for g in W.walk_words(tree, kids_of, describe)]
    check("off-screen controls are skipped and so is everything inside them",
          "scrolled away" not in got and "inside hidden" not in got, str(got))
    check("... on-screen ones are read, and their children", got[:1] == ["visible one"]
          and "visible two" in got and "visible child" in got, str(got))
    check("... and the children of a skipped control were never even asked for", "scrolled away" not in visited)
    check("a control whose off-screen answer is 'unknown' is read like an ordinary one (the reader itself "
          "treats a failed question as off screen)", "unsure" in got)
    pw = N("root", [N("Password", [N("hunter2")], password=True), N("Name")])
    got = W.walk_words(pw, kids_of, describe)
    check("a password box is still marked, with nothing of it or inside it",
          {"text": "", "password": True} in got and "Password" not in repr(got) and "hunter2" not in repr(got))
    check("the walk has a quarter-second budget", W.UI_TIME_BUDGET_S == 0.25 and W.UI_NODE_BUDGET >= 100)
    import inspect
    src = inspect.getsource(W.ui_text)
    check("the real reader asks 'off screen?' and treats a failed answer as yes",
          "IsOffscreen" in src and "off = True" in src)
    check("... and does not fetch a value for a password box (it returns before the value)",
          src.index("if pw:") < src.index("ValuePattern"))


def main():
    for fn in (t_subtract, t_masks, t_browsers, t_pieces, t_take, t_walk):
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
