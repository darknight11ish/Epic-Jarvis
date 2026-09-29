"""jarvis_screen_win.py - the Windows readers "Look at this" and "Watch with
me" need: what is in front (with the password-box and capture-protection
checks), the picture, and the window's own text.

NEW MODULE, shipped whole (apply-patches.ps1 copies it beside jarvis_hud.py;
no patch). docs/SCREEN-DESIGN.md build step 3, built 2026-09-29. It is the
Windows half of jarvis_screen.py: the rules (jarvis_screen.pause_reason and
the rest) never call Windows themselves; they are handed these three readers.

WHAT IS TESTED, AND WHAT IS NOT
  * Tested here (backend/test_screen_win.py), on any machine: the PNG writer
    (a picture's raw pixels become a PNG in memory, a decoder reads it back),
    the half-size fallback, the desktop-name lock rule, the rectangle
    clipping, and the window-text walk (a fake control tree with a password
    box: its words never appear).
  * NOT tested here - written against Windows' own documentation and run
    only on the owner's PC: every ctypes call (GetForegroundWindow,
    GetWindowDisplayAffinity, BitBlt, GetDIBits, OpenInputDesktop) and every
    UI Automation call (`uiautomation`, the package control_computer already
    uses). The one unverified thing that matters most: whether a browser's
    password box says `IsPassword` to UI Automation in every browser. It
    does in Chrome and Edge once accessibility is on, which asking for it
    turns on; Firefox and custom-drawn programs may not - the design says
    so plainly ("programs that do not mark password boxes").

SCREEN SAFETY (2026-09-29, the owner's "all three"): the picture is taken with
every window Jarvis must not show painted SOLID BLACK - not only the one in
front. The window list (`_list_windows`, EnumWindows, top of the stack first)
is read just before and just after the grab; `must_hide` says which windows
go black (a program on the Never look at list, a private browser window,
Jarvis's own windows, the lock screen and admin prompts, and a browser that is
not in front on a listed site or whose site cannot be read); `mask_rects`
takes away what an OPAQUE window in front already hides (a see-through or
click-through one never counts - it could be an invisible overlay); and
`take_picture` fails closed: no Never look at list, no window list, no
picture. The rules are tested on any machine (backend/test_screen_masks.py);
EnumWindows and the address-box reads are not run here. The window's own text
walk skips off-screen controls, never reads a password box's value, and has a
quarter-second budget.

FAIL SAFE. Any check that raises or cannot answer returns None, which
jarvis_screen.pause_reason turns into a pause ("cannot_check"), never a
look. Nothing here is written to disk: the picture is bytes in memory, the
PNG is bytes in memory, and the caller drops both after reading.
"""
from __future__ import annotations

import ntpath
import os
import struct
import time
import zlib
from typing import Callable, Iterable, Optional

try:
    import jarvis_front as front
except Exception:  # pragma: no cover - shipped beside it
    front = None  # type: ignore

#: Node budget and time budget for the window-text walk.
UI_NODE_BUDGET = 700
UI_TIME_BUDGET_S = 0.25
UI_DEPTH = 14

# --------------------------------------------------------------------------
#   Pure helpers (tested on any machine)
# --------------------------------------------------------------------------


def png_from_bgra(bgra: bytes, width: int, height: int, *, level: int = 3) -> bytes:
    """A PNG (RGB, no alpha) from raw top-down BGRA pixels, all in memory.
    Pure Python + zlib: no Pillow needed. `bgra` is width*height*4 bytes."""
    n = width * height
    if width <= 0 or height <= 0 or len(bgra) < n * 4:
        raise ValueError("the pixels do not match the size")
    view = memoryview(bgra)
    rgb = bytearray(n * 3)
    rgb[0::3] = view[2:n * 4:4]     # red
    rgb[1::3] = view[1:n * 4:4]     # green
    rgb[2::3] = view[0:n * 4:4]     # blue
    return _png_from_rgb(bytes(rgb), width, height, level)


def _png_from_rgb(rgb: bytes, width: int, height: int, level: int = 3) -> bytes:
    stride = width * 3
    raw = bytearray((stride + 1) * height)
    for y in range(height):
        o = y * (stride + 1)
        raw[o] = 0                                   # filter: none
        raw[o + 1:o + 1 + stride] = rgb[y * stride:(y + 1) * stride]

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), level))
            + chunk(b"IEND", b""))


def png_half_size(bgra: bytes, width: int, height: int, *, level: int = 3) -> bytes:
    """The same picture at half the width and height (every second pixel of
    every second row) - the fallback when the full PNG is too big for the
    text reader. Text stays readable at half size on a 4K screen."""
    w2, h2 = max(1, width // 2), max(1, height // 2)
    view = memoryview(bgra)
    out = bytearray(w2 * h2 * 4)
    for y in range(h2):
        src = (y * 2) * width * 4
        row = view[src:src + width * 4]
        dst = y * w2 * 4
        for c in range(4):
            out[dst + c:dst + w2 * 4:4] = row[c:(w2 * 2) * 4:8][:w2]
    return png_from_bgra(bytes(out), w2, h2, level=level)


def locked_from_desktop(name: Optional[str], access_denied: bool) -> Optional[bool]:
    """True on the lock screen, False while someone is working, None when it
    cannot be told - the same rule as the desktop app's live.rs. The input
    desktop is "Default" while someone is signed in and working; on the lock
    screen this process is refused it (access denied); "Winlogon" is also the
    secure desktop a User Account Control prompt shows, which is a pause, not
    a lock."""
    if name is not None:
        return False if str(name).lower() == "default" else None
    return True if access_denied else None


def clip_rect(rect: tuple, screen: tuple) -> Optional[tuple]:
    """(left, top, right, bottom) of `rect` inside `screen`, or None when
    nothing of it is on screen or it is empty."""
    l, t = max(rect[0], screen[0]), max(rect[1], screen[1])
    r, b = min(rect[2], screen[2]), min(rect[3], screen[3])
    return (l, t, r, b) if r - l >= 8 and b - t >= 8 else None


#: How far a masked rectangle is grown on every side, in pixels, so the
#: window's shadow and the frame's rounding never leave a line of it showing.
MASK_MARGIN = 2
#: The most rectangles one window may be cut into before its whole frame is
#: painted instead (a safe over-cover).
MASK_MAX_PIECES = 200
#: How many browser windows' address boxes are read per picture; a browser
#: past that is treated as "cannot tell which site", so it is hidden.
ADDRESS_MAX_WINDOWS = 4


def subtract_rects(rect: tuple, cutters) -> list:
    """The parts of `rect` (left, top, right, bottom) that none of `cutters`
    covers, as a list of rectangles. Pure geometry."""
    pieces = [tuple(rect)]
    for c in cutters:
        nxt = []
        for (l, t, r, b) in pieces:
            il, it, ir, ib = max(l, c[0]), max(t, c[1]), min(r, c[2]), min(b, c[3])
            if ir <= il or ib <= it:
                nxt.append((l, t, r, b))
                continue
            if it > t:
                nxt.append((l, t, r, it))
            if ib < b:
                nxt.append((l, ib, r, b))
            if il > l:
                nxt.append((l, it, il, ib))
            if ir < r:
                nxt.append((ir, it, r, ib))
        pieces = nxt
        if not pieces:
            break
    return pieces


def _grow(rect: tuple, by: int) -> tuple:
    return (rect[0] - by, rect[1] - by, rect[2] + by, rect[3] + by)


def _clip(rect: tuple, to: tuple) -> Optional[tuple]:
    l, t, r, b = max(rect[0], to[0]), max(rect[1], to[1]), min(rect[2], to[2]), min(rect[3], to[3])
    return (l, t, r, b) if r > l and b > t else None


def must_hide(w: dict, never, *, front_hwnd=None,
              address_of: Optional[Callable] = None) -> bool:
    """Is this window one Jarvis must never show in a picture?
      * a program on the owner's Never look at list (and the lock screen and
        admin prompts, which are never on it);
      * one of Jarvis's own windows;
      * a private browser window;
      * a browser window, not the one in front, showing a site on the list -
        or one whose site cannot be read while the list holds sites (the
        same "cannot tell" rule as a pause).
    `address_of(w)` gives that window's site ("" when it cannot be read)."""
    import jarvis_screen as S            # the lists and the words live there
    exe = ntpath.basename(str(w.get("exe") or "")).lower()
    if not exe:
        return False
    if never.has_program(exe) or exe in S.LOCK_EXES or exe in S.ADMIN_EXES:
        return True
    if front is not None and (exe in front.JARVIS_EXES
                              or front._is_jarvis_title(str(w.get("title") or ""))):
        return True
    if front is not None and exe in front.BROWSERS:
        if S.is_private_title(w.get("title")):
            return True
        if never.holds_sites() and w.get("hwnd") != front_hwnd:
            site = address_of(w) if address_of else ""
            return (not site) or never.has_site(site)
    return False


def mask_rects(windows: list, *, capture_rect: tuple, never, front_hwnd=None,
               address_of: Optional[Callable] = None) -> list:
    """The rectangles (screen pixels, inside `capture_rect`) to paint black.
    `windows` are the visible windows top of the stack first, each {"hwnd",
    "exe", "title", "rect": (l, t, r, b), "opaque": bool}. For every window
    that must_hide, its rectangle minus the part hidden behind an OPAQUE
    window above it (a window that is see-through or lets clicks through
    never counts as hiding anything - it could be an invisible overlay),
    grown by MASK_MARGIN and clipped to the picture. Fail closed: a window
    cut into too many pieces is painted whole. Never asks `address_of` about
    a window that is entirely hidden."""
    out = []
    asked = [0]

    def site_of(w) -> str:
        if address_of is None:
            return ""
        asked[0] += 1
        if asked[0] > ADDRESS_MAX_WINDOWS:
            return ""
        try:
            return str(address_of(w) or "")
        except Exception:
            return ""

    above: list = []
    for w in windows:
        rect = _clip(tuple(w["rect"]), capture_rect)
        if rect is not None:
            parts = subtract_rects(rect, above)
            if parts and must_hide(w, never, front_hwnd=front_hwnd, address_of=site_of):
                if len(parts) > MASK_MAX_PIECES:
                    parts = [rect]
                for p in parts:
                    g = _clip(_grow(p, MASK_MARGIN), capture_rect)
                    if g:
                        out.append(g)
        if w.get("opaque"):
            r = _clip(tuple(w["rect"]), capture_rect)
            if r:
                above.append(r)
    return out


def local_boxes(rects: list, capture_rect: tuple) -> list:
    """Screen rectangles as boxes in the picture's own pixels."""
    l0, t0 = capture_rect[0], capture_rect[1]
    return [(r[0] - l0, r[1] - t0, r[2] - l0, r[3] - t0) for r in rects]


def walk_words(root, children: Callable, describe: Callable, *,
               budget: int = UI_NODE_BUDGET, seconds: float = UI_TIME_BUDGET_S,
               depth: int = UI_DEPTH, clock: Callable[[], float] = time.monotonic) -> list:
    """The window's own labels and text boxes, as [{"text", "password"}].
    `children(control)` lists a control's children; `describe(control)` gives
    {"type", "name", "value", "password"}. A password box is marked AND its
    label and value are left out here already (jarvis_screen.ui_words skips a
    marked one a second time - two locks). Bounded by a node count and a
    time. Text boxes give their value, everything else its name; the same
    words are never listed twice in a row."""
    out: list = []
    seen = [0]
    t0 = clock()

    def add(text) -> None:
        t = " ".join(str(text or "").split())
        if t and (not out or out[-1]["text"] != t):
            out.append({"text": t, "password": False})

    def go(node, d: int) -> None:
        if d <= 0 or seen[0] >= budget or clock() - t0 > seconds:
            return
        try:
            kids = children(node)
        except Exception:
            return
        for k in kids or []:
            if seen[0] >= budget or clock() - t0 > seconds:
                return
            seen[0] += 1
            try:
                info = describe(k) or {}
            except Exception:
                info = {"password": True}       # cannot tell: leave it out
            if info.get("password") is not False and info.get("password") is not None:
                # True, or anything odd: skipped, and so is everything in it
                out.append({"text": "", "password": True})
                continue
            if info.get("offscreen") is not False and info.get("offscreen") is not None:
                continue                        # off screen (or cannot tell): not read, nor what is in it
            kind = str(info.get("type") or "")
            if kind in ("EditControl", "DocumentControl"):
                add(info.get("value") or info.get("name"))
            else:
                add(info.get("name"))
            go(k, d - 1)

    go(root, depth)
    return [o for o in out if o["password"] or o["text"]]


# --------------------------------------------------------------------------
#   Windows (ctypes) - not run in the development container
# --------------------------------------------------------------------------

_HAVE: dict = {}


def available() -> bool:
    """Can this PC look at the screen at all: Windows, and the `uiautomation`
    package the password check needs. Cached."""
    if "ok" not in _HAVE:
        ok = os.name == "nt"
        if ok:
            try:
                import uiautomation  # type: ignore  # noqa: F401
            except Exception:
                ok = False
        _HAVE["ok"] = ok
    return bool(_HAVE["ok"])


def unavailable_why() -> str:
    if os.name != "nt":
        return "This is not Windows."
    if not available():
        return ("The 'uiautomation' package is missing, and Jarvis will not look at the screen "
                "without it: it is what tells a password box from any other box. Run "
                "scripts\\apply-patches.ps1 again on the PC to install it.")
    return ""


def _user32():
    import ctypes
    return ctypes.WinDLL("user32", use_last_error=True)


def _locked_now() -> Optional[bool]:
    """The lock-screen check: the input desktop's name, like live.rs."""
    import ctypes
    from ctypes import wintypes
    user32 = _user32()
    user32.OpenInputDesktop.restype = wintypes.HANDLE
    user32.OpenInputDesktop.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    user32.CloseDesktop.argtypes = (wintypes.HANDLE,)
    user32.GetUserObjectInformationW.argtypes = (
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD))
    desk = user32.OpenInputDesktop(0, False, 0x0001)      # DESKTOP_READOBJECTS
    if not desk:
        return locked_from_desktop(None, ctypes.get_last_error() == 5)
    try:
        buf = ctypes.create_unicode_buffer(64)
        need = wintypes.DWORD(0)
        if not user32.GetUserObjectInformationW(desk, 2, buf, ctypes.sizeof(buf),
                                                ctypes.byref(need)):     # UOI_NAME
            return None
        return locked_from_desktop(buf.value, False)
    finally:
        user32.CloseDesktop(desk)


def _capture_protected(hwnd) -> Optional[bool]:
    """True when the window asks not to be captured (SetWindowDisplayAffinity
    other than "none"), None when the question cannot be answered."""
    import ctypes
    from ctypes import wintypes
    user32 = _user32()
    user32.GetWindowDisplayAffinity.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    aff = wintypes.DWORD(0)
    if not user32.GetWindowDisplayAffinity(hwnd, ctypes.byref(aff)):
        return None
    return aff.value != 0


def _password_focused() -> Optional[bool]:
    """Is the focused control a password box (UI Automation `IsPassword`)?
    None when UI Automation cannot say - a pause, never a look."""
    try:
        import uiautomation as auto  # type: ignore
    except Exception:
        return None
    try:
        with front._thread_context():
            c = auto.GetFocusedControl()
            if c is None:
                return False
            flag = c.IsPassword
            return bool(flag) if flag is not None else None
    except Exception:
        return None


def front_snapshot() -> Optional[dict]:
    """One fresh reading of what is in front, in the shape
    jarvis_screen.pause_reason wants: {"exe", "title", "cls", "host",
    "hwnd", "password_focused", "capture_protected", "locked"}. None when
    nothing can be read (a secure desktop, no window)."""
    locked = _locked_now()
    if locked is True:
        return {"exe": "", "title": "", "cls": "", "host": "", "hwnd": None, "locked": True}
    if locked is None:
        return None
    got = front._windows_front()
    if got is None:
        return None
    exe = ntpath.basename(str(got.get("exe") or "")).lower()
    host = ""
    if exe in front.BROWSERS:
        try:
            with front._thread_context():
                host = front.host_of(front._address_box_value(got["hwnd"], front.BROWSERS[exe]))
        except Exception:
            host = ""
    hwnd = got.get("hwnd")
    try:
        hwnd_key = int(hwnd) if hwnd is not None else None
    except (TypeError, ValueError):
        hwnd_key = None
    return {"exe": got.get("exe"), "title": got.get("title"), "cls": got.get("cls"),
            "host": host, "hwnd": hwnd_key, "locked": False,
            "capture_protected": _capture_protected(hwnd),
            "password_focused": _password_focused()}


def _rect_of(hwnd, whole: bool) -> Optional[tuple]:
    """(left, top, right, bottom) in screen pixels: the window in front
    (its visible frame), or with `whole` the whole monitor it is on."""
    import ctypes
    from ctypes import wintypes
    user32 = _user32()

    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", RECT), ("rcWork", RECT),
                    ("dwFlags", wintypes.DWORD)]

    user32.IsIconic.argtypes = (wintypes.HWND,)
    if hwnd and user32.IsIconic(hwnd):
        return None                                    # minimised: nothing to see
    if whole:
        user32.MonitorFromWindow.restype = wintypes.HANDLE
        user32.MonitorFromWindow.argtypes = (wintypes.HWND, wintypes.DWORD)
        user32.GetMonitorInfoW.argtypes = (wintypes.HANDLE, ctypes.POINTER(MONITORINFO))
        mon = user32.MonitorFromWindow(hwnd, 2)        # MONITOR_DEFAULTTONEAREST
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if not mon or not user32.GetMonitorInfoW(mon, ctypes.byref(info)):
            return None
        r = info.rcMonitor
        return (r.left, r.top, r.right, r.bottom)
    rect = RECT()
    got = False
    try:
        dwm = ctypes.WinDLL("dwmapi")
        # DWMWA_EXTENDED_FRAME_BOUNDS: the visible frame, without the
        # invisible resize border GetWindowRect includes.
        got = dwm.DwmGetWindowAttribute(wintypes.HWND(hwnd), 9, ctypes.byref(rect),
                                        ctypes.sizeof(rect)) == 0
    except Exception:
        got = False
    if not got:
        user32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(RECT))
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return None
    screen = (user32.GetSystemMetrics(76), user32.GetSystemMetrics(77),
              user32.GetSystemMetrics(76) + user32.GetSystemMetrics(78),
              user32.GetSystemMetrics(77) + user32.GetSystemMetrics(79))
    return clip_rect((rect.left, rect.top, rect.right, rect.bottom), screen)


def _grab_bgra(rect: tuple) -> Optional[tuple]:
    """(BGRA bytes, width, height) of `rect` on screen, in memory."""
    import ctypes
    from ctypes import wintypes
    user32 = _user32()
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    left, top, right, bottom = rect
    w, h = right - left, bottom - top

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long),
                    ("biHeight", ctypes.c_long), ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                    ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]

    user32.GetDC.restype = wintypes.HDC
    user32.GetDC.argtypes = (wintypes.HWND,)
    user32.ReleaseDC.argtypes = (wintypes.HWND, wintypes.HDC)
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateCompatibleDC.argtypes = (wintypes.HDC,)
    gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    gdi32.CreateCompatibleBitmap.argtypes = (wintypes.HDC, ctypes.c_int, ctypes.c_int)
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.SelectObject.argtypes = (wintypes.HDC, wintypes.HGDIOBJ)
    gdi32.BitBlt.argtypes = (wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                             ctypes.c_int, wintypes.HDC, ctypes.c_int, ctypes.c_int,
                             wintypes.DWORD)
    gdi32.GetDIBits.argtypes = (wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
                                ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT)
    gdi32.DeleteObject.argtypes = (wintypes.HGDIOBJ,)
    gdi32.DeleteDC.argtypes = (wintypes.HDC,)

    screen = user32.GetDC(None)
    if not screen:
        return None
    mem = gdi32.CreateCompatibleDC(screen)
    bmp = gdi32.CreateCompatibleBitmap(screen, w, h)
    try:
        if not mem or not bmp:
            return None
        old = gdi32.SelectObject(mem, bmp)
        # SRCCOPY | CAPTUREBLT: layered windows are included; a window that
        # asked not to be captured comes out black or missing.
        ok = gdi32.BitBlt(mem, 0, 0, w, h, screen, left, top, 0x00CC0020 | 0x40000000)
        if not ok:
            return None
        bi = BITMAPINFOHEADER()
        bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bi.biWidth, bi.biHeight = w, -h                 # top-down
        bi.biPlanes, bi.biBitCount, bi.biCompression = 1, 32, 0
        buf = (ctypes.c_ubyte * (w * h * 4))()
        gdi32.SelectObject(mem, old)
        got = gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bi), 0)
        if got != h:
            return None
        return bytes(buf), w, h
    finally:
        if bmp:
            gdi32.DeleteObject(bmp)
        if mem:
            gdi32.DeleteDC(mem)
        user32.ReleaseDC(None, screen)


#: The biggest PNG handed to the text reader (jarvis_ocr.MAX_BYTES).
def _max_png() -> int:
    try:
        import jarvis_ocr
        return int(jarvis_ocr.MAX_BYTES)
    except Exception:
        return 4 * 1024 * 1024


def _exe_of_hwnd(hwnd) -> str:
    """The program file behind a window ("" when it cannot be told)."""
    import ctypes
    from ctypes import wintypes
    user32 = _user32()
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.QueryFullProcessImageNameW.argtypes = (
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    def exe_of_pid(p) -> str:
        h = kernel32.OpenProcess(0x1000, False, p)          # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return ""
        try:
            size = wintypes.DWORD(1024)
            buf = ctypes.create_unicode_buffer(1024)
            return buf.value if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)) else ""
        finally:
            kernel32.CloseHandle(h)

    exe = exe_of_pid(pid.value)
    if ntpath.basename(exe).lower() == "applicationframehost.exe":
        # A Store (UWP) app: the frame belongs to ApplicationFrameHost and the app
        # itself is a child window of another process - the same unwrap
        # jarvis_front.py does for the window in front, so the black-out mask
        # sees the real program name (a Store app on the Never look at list is
        # painted over). Any failure keeps the frame host's own name.
        try:
            found = []
            proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

            def each(child, _l):
                cpid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(child, ctypes.byref(cpid))
                if cpid.value and cpid.value != pid.value:
                    found.append(cpid.value)
                    return False
                return True
            user32.EnumChildWindows(hwnd, proc(each), 0)
            if found:
                exe = exe_of_pid(found[0]) or exe
        except Exception:
            pass
    return exe


def _list_windows() -> Optional[list]:
    """The visible top-level windows on the desktop, TOP OF THE STACK FIRST
    (the order EnumWindows gives): [{"hwnd", "exe", "title", "rect": (l, t,
    r, b), "opaque"}]. Minimised windows and windows Windows "cloaks" (on
    another virtual desktop, or suspended) are left out - neither is on
    screen. `opaque` is False for a window that is see-through or lets clicks
    pass through (WS_EX_LAYERED or WS_EX_TRANSPARENT): it could be an invisible
    overlay, so it never counts as hiding what is behind it.

    None when the list cannot be read - FAIL CLOSED: the caller then hands
    on no picture at all. Not run in the development container."""
    import ctypes
    from ctypes import wintypes
    try:
        user32 = _user32()
        dwm = ctypes.WinDLL("dwmapi")

        class RECT(ctypes.Structure):
            _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                        ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

        enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.IsWindowVisible.argtypes = (wintypes.HWND,)
        user32.IsIconic.argtypes = (wintypes.HWND,)
        user32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(RECT))
        user32.GetWindowLongW.restype = ctypes.c_long
        user32.GetWindowLongW.argtypes = (wintypes.HWND, ctypes.c_int)
        user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
        user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
        user32.EnumWindows.argtypes = (enum_proc, wintypes.LPARAM)
        out: list = []
        bad = [0]

        def each(hwnd, _lparam):
            try:
                if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
                    return True
                cloaked = wintypes.DWORD(0)
                if dwm.DwmGetWindowAttribute(wintypes.HWND(hwnd), 14, ctypes.byref(cloaked),
                                             ctypes.sizeof(cloaked)) == 0 and cloaked.value:
                    return True                      # DWMWA_CLOAKED
                r = RECT()
                # DWMWA_EXTENDED_FRAME_BOUNDS: the visible frame; the plain rectangle
                # includes an invisible resize border.
                if dwm.DwmGetWindowAttribute(wintypes.HWND(hwnd), 9, ctypes.byref(r),
                                             ctypes.sizeof(r)) != 0:
                    if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
                        bad[0] += 1
                        return True
                if r.right - r.left <= 0 or r.bottom - r.top <= 0:
                    return True
                ex = user32.GetWindowLongW(hwnd, -20) & 0xFFFFFFFF      # GWL_EXSTYLE
                n = max(0, int(user32.GetWindowTextLengthW(hwnd)))
                tbuf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, tbuf, n + 1)
                out.append({"hwnd": int(hwnd), "exe": _exe_of_hwnd(hwnd), "title": tbuf.value,
                            "rect": (r.left, r.top, r.right, r.bottom),
                            "opaque": not (ex & 0x00080000 or ex & 0x00000020)})
            except Exception:
                bad[0] += 1
            return True

        if not user32.EnumWindows(enum_proc(each), 0):
            return None
        return None if bad[0] else out
    except Exception:
        return None


def _address_of(w: dict) -> str:
    """The SITE a browser window shows (the host of its address box, "" when
    it cannot be read). Slow (UI Automation) - asked only for a browser
    window with something visible in the picture."""
    exe = ntpath.basename(str(w.get("exe") or "")).lower()
    family = front.BROWSERS.get(exe) if front is not None else None
    if not family:
        return ""
    with front._thread_context():
        return front.site_of(front.host_of(front._address_box_value(w["hwnd"], family)))


def take_picture(snap: dict, whole: bool, never, *, rect_of: Callable, grab: Callable,
                 list_windows: Callable, address_of: Callable) -> Optional[bytes]:
    """The whole safe capture, with every Windows call handed in (so the
    rules are tested on any machine): the rectangle, the window list just
    BEFORE the grab, the grab, the window list just AFTER it (a window that
    opened or closed while it ran is covered too), every window that must be
    hidden painted SOLID BLACK on the pixels, then the PNG.

    FAIL CLOSED - None, no picture at all - when: there is no Never look at
    list or it cannot be read; the rectangle, the grab or EITHER window list
    cannot be had; anything in the masking raises."""
    if never is None or getattr(never, "broken", True):
        return None
    try:
        rect = rect_of(snap["hwnd"], whole)
        if rect is None:
            return None
        before = list_windows()
        got = grab(rect)
        after = list_windows()
        if got is None or before is None or after is None:
            return None
        seen: dict = {}

        def address(w) -> str:
            if w["hwnd"] not in seen:
                seen[w["hwnd"]] = address_of(w)
            return seen[w["hwnd"]]

        rects = []
        for wins in (before, after):
            rects += mask_rects(wins, capture_rect=rect, never=never,
                                front_hwnd=snap["hwnd"], address_of=address)
        bgra, w, h = got
        if rects:
            import jarvis_picture
            pix = bytearray(bgra)
            jarvis_picture.paint_black(pix, w, h, local_boxes(rects, rect))
            bgra = bytes(pix)
        png = png_from_bgra(bgra, w, h)
        if len(png) > _max_png() and w >= 16 and h >= 16:
            png = png_half_size(bgra, w, h)
        return png if len(png) <= _max_png() else None
    except Exception:
        return None


def capture(snap: dict, whole: bool = False, never=None) -> Optional[bytes]:
    """The picture: a PNG of the window in front (or, with `whole`, its
    whole monitor), in memory, with every window Jarvis must not show
    painted SOLID BLACK (see must_hide and take_picture). `never` is the
    owner's Never look at list (jarvis_screen.NeverLook). None when it cannot
    be taken OR cannot be made safe: FAIL CLOSED. Never touches the disk."""
    import ctypes
    if os.name != "nt" or not isinstance(snap, dict) or snap.get("hwnd") is None:
        return None
    if never is None or getattr(never, "broken", True):
        return None
    user32 = _user32()
    old = None
    try:
        # Per-monitor DPI awareness for THIS thread only, so window
        # rectangles and screen pixels agree on a scaled display.
        try:
            user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
            user32.SetThreadDpiAwarenessContext.argtypes = (ctypes.c_void_p,)
            old = user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
        except Exception:
            old = None
        return take_picture(snap, whole, never, rect_of=_rect_of, grab=_grab_bgra,
                            list_windows=_list_windows, address_of=_address_of)
    except Exception:
        return None
    finally:
        if old:
            try:
                user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(old))
            except Exception:
                pass


def ui_text(snap: dict) -> list:
    """The window in front's own labels and text boxes, every password box
    skipped, as [{"text", "password"}] (see walk_words). [] when it cannot be
    read - the picture's words still come from the text recognition."""
    if not isinstance(snap, dict) or snap.get("hwnd") is None:
        return []
    try:
        import uiautomation as auto  # type: ignore
    except Exception:
        return []

    def children(c):
        return c.GetChildren()

    def describe(c) -> dict:
        try:
            pw = c.IsPassword
        except Exception:
            pw = True
        if pw is None:
            pw = True                        # cannot tell: treated as a password box
        if pw:
            return {"password": True}
        try:
            off = c.IsOffscreen
        except Exception:
            off = True
        if off is None or off:               # off screen, or cannot tell: not read
            return {"offscreen": True, "password": False}
        kind = c.ControlTypeName
        value = ""
        if kind in ("EditControl", "DocumentControl"):
            try:
                p = c.GetPattern(auto.PatternId.ValuePattern)
                value = str(p.Value or "") if p is not None else ""
            except Exception:
                value = ""
        return {"type": kind, "name": c.Name, "value": value, "password": False, "offscreen": False}

    try:
        with front._thread_context():
            root = auto.ControlFromHandle(snap["hwnd"])
            if root is None:
                return []
            return walk_words(root, children, describe)
    except Exception:
        return []


def readers(never=None) -> dict:
    """The three readers jarvis_screen.Screen is built from. `never` is the
    owner's Never look at list, or a function that gives it (the picture
    cannot be taken without it - it is what says which windows to paint
    black)."""
    def take(snap: dict, whole: bool = False) -> Optional[bytes]:
        return capture(snap, whole, never=never() if callable(never) else never)

    return {"front_reader": front_snapshot, "capture": take, "ui_text": ui_text}
