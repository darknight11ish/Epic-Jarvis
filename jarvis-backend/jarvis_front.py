"""jarvis_front.py - what is in front on this PC: the one front-window reader
that focus sessions and "Watch with me" share.

NEW MODULE, shipped whole (apply-patches.ps1 copies it beside jarvis_hud.py;
no patch). Split out of jarvis_focus.py on 2026-09-28, word for word, for
docs/SCREEN-DESIGN.md build step 1: "Focus's front-app reader
(`jarvis_focus.windows_probe`, `_address_box_value`) moves into a shared
`jarvis_front.py`; one once-a-second reader serves both." jarvis_focus.py
imports every name here back under its old name, so nothing that called
`jarvis_focus.windows_probe` or `jarvis_focus.host_of` changed.

WHAT IT READS, AND WHAT IT NEVER READS
  * The window in front: its program (the .exe path), its title and its
    window class - `_windows_front()`, ctypes only.
  * For a web browser, the HOST of the front tab (e.g. "youtube.com"), read
    from the address box through UI Automation and cut down to the host at
    once (`host_of`). The rest of the address is dropped inside this module.
  * Never the page itself: a Document control is never walked into, and at
    most _UIA_READ_BUDGET controls are visited.
  * It keeps nothing. Every call reads fresh and returns a small dict; what
    the caller does with it is the caller's business (focus turns it into
    salted fingerprints; jarvis_screen.py uses it only to decide whether to
    pause).

The Windows half (`_windows_front`, `_address_box_value`, `windows_probe`)
needs Windows and the `uiautomation` package and is not run in the
development container; the host parsing is plain Python and is tested
(backend/test_front.py, and every focus test through jarvis_focus).
"""
from __future__ import annotations

import ntpath
import os
import re
import urllib.parse
from typing import Optional

#: Web browsers: exe -> the kind of address box they have.
BROWSERS = {"chrome.exe": "chromium", "msedge.exe": "chromium", "brave.exe": "chromium",
            "vivaldi.exe": "chromium", "opera.exe": "chromium", "firefox.exe": "firefox"}
#: Jarvis's own programs: home base. Tauri names the file after the Cargo
#: package or the product name, so both.
JARVIS_EXES = ("jarvis-desktop.exe", "jarvis desktop.exe", "jarvis_desktop.exe")
#: Windows' own surfaces that are nowhere in particular: the desktop, the
#: taskbar, Alt+Tab, the Start menu, the lock screen. Neither on target nor
#: a drift.
NEUTRAL_CLASSES = ("Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd",
                   "MultitaskingViewFrame", "XamlExplorerHostIslandWindow",
                   "ForegroundStaging", "TaskSwitcherWnd", "TopLevelWindowForOverflowXamlIsland")
NEUTRAL_EXES = ("lockapp.exe", "startmenuexperiencehost.exe", "searchhost.exe",
                "searchapp.exe", "shellexperiencehost.exe", "searchui.exe")

_HOST_RX = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}$")


def host_of(address: str) -> str:
    """The host of what a browser's address box says, or "" when it is not an
    address (the owner is typing a search there). The rest of the address
    is dropped here and never kept."""
    a = str(address or "").strip()
    if not a or " " in a or len(a) > 2048:
        return ""
    if "://" not in a:
        a = "http://" + a
    try:
        host = (urllib.parse.urlsplit(a).hostname or "").lower().rstrip(".")
    except ValueError:
        return ""
    if host == "localhost" or re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", host):
        return host
    return host if _HOST_RX.fullmatch(host) else ""


def site_of(host: str) -> str:
    """What counts as one site: the host without "www." or "m." in front, so
    www.youtube.com and m.youtube.com are one, and docs.google.com and
    mail.google.com are two."""
    h = str(host or "").lower()
    for lead in ("www.", "m.", "mobile."):
        if h.startswith(lead) and h.count(".") >= 2:
            h = h[len(lead):]
    return h


def _registrable(host: str) -> str:
    parts = host.split(".")
    if len(parts) >= 3 and len(parts[-1]) == 2 and parts[-2] in (
            "co", "com", "org", "net", "ac", "gov", "edu", "ltd", "plc"):
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def _is_jarvis_title(title: str) -> bool:
    try:
        import jarvis_ui_control
        return bool(jarvis_ui_control.is_jarvis_window(title))
    except Exception:
        return re.match(r"jarvis(?![\w'])", " ".join(str(title or "").split()), re.I) is not None


# ---- the Windows probe (not run in this container; see the header) ---------

_UIA_READ_BUDGET = 400      # nodes walked looking for the address box
_UIA_READ_DEPTH = 12


def _windows_front() -> Optional[dict]:
    """{"exe", "title", "cls", "hwnd"} of the window in front, read fresh.
    ctypes only. None when nothing is in front or it cannot be read."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
    user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.QueryFullProcessImageNameW.argtypes = (
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)

    def exe_of_pid(pid: int) -> str:
        h = kernel32.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return ""
        try:
            size = wintypes.DWORD(1024)
            buf = ctypes.create_unicode_buffer(1024)
            if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                return buf.value
            return ""
        finally:
            kernel32.CloseHandle(h)

    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    cbuf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, cbuf, 256)
    n = max(0, int(user32.GetWindowTextLengthW(hwnd)))
    tbuf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, tbuf, n + 1)
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    exe = exe_of_pid(pid.value)
    if ntpath.basename(exe).lower() == "applicationframehost.exe":
        # A Store app: the frame belongs to ApplicationFrameHost, and the
        # app itself is a child window of another process.
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
    return {"exe": exe, "title": tbuf.value, "cls": cbuf.value, "hwnd": hwnd}


def _address_box_value(hwnd, family: str) -> str:
    """The text in a browser window's address box, through UI Automation.
    Never looks inside the page itself (a Document is not walked into), and
    walks at most _UIA_READ_BUDGET nodes. "" when it cannot be read."""
    import uiautomation as auto  # type: ignore
    win = auto.ControlFromHandle(hwnd)
    if win is None:
        return ""
    seen = [0]

    def value_of(c) -> str:
        # GetPattern(PatternId.ValuePattern) works on any control - the same
        # call jarvis_ui_control._default_act uses for a "read" step.
        try:
            p = c.GetPattern(auto.PatternId.ValuePattern)
            return str(p.Value or "") if p is not None else ""
        except Exception:
            return ""

    def walk(c, depth: int, in_toolbar: bool) -> str:
        if depth <= 0 or seen[0] >= _UIA_READ_BUDGET:
            return ""
        try:
            kids = c.GetChildren()
        except Exception:
            return ""
        for k in kids:
            seen[0] += 1
            try:
                ctype = k.ControlTypeName
            except Exception:
                continue
            if ctype == "DocumentControl":
                continue            # the page itself: never read
            if ctype == "EditControl":
                aid = str(getattr(k, "AutomationId", "") or "")
                if (family == "firefox" and aid == "urlbar-input") or \
                        (family != "firefox" and in_toolbar):
                    return value_of(k)
            got = walk(k, depth - 1, in_toolbar or ctype == "ToolBarControl")
            if got:
                return got
        return ""
    return walk(win, _UIA_READ_DEPTH, False)


def windows_probe() -> Optional[dict]:
    """The real reading, on Windows: the program in front, its title (only
    to tell Jarvis's own windows apart - dropped at once), its class, and
    for a browser the HOST of the front tab (the address is cut down to the
    host inside this function)."""
    front = _windows_front()
    if front is None:
        return None
    exe = ntpath.basename(str(front.get("exe") or "")).lower()
    host = ""
    if exe in BROWSERS:
        try:
            host = host_of(_address_box_value(front["hwnd"], BROWSERS[exe]))
        except Exception:
            host = ""
    return {"exe": front.get("exe"), "title": front.get("title"), "cls": front.get("cls"),
            "host": host}


def probe_available() -> bool:
    return os.name == "nt"


class _NoThreadContext:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _thread_context():
    """UI Automation needs COM set up on the thread that uses it (the look
    thread). A no-op when the package is missing or off Windows."""
    if os.name != "nt":
        return _NoThreadContext()
    try:
        import uiautomation as auto  # type: ignore
        return auto.UIAutomationInitializerInThread(debug=False)
    except Exception:
        return _NoThreadContext()
