"""jarvis_focus.py - focus sessions: a timer plus Quiet, and Jarvis keeping
the owner honest about what is in front of them ON THIS PC.

NEW MODULE, shipped whole (apply-patches.ps1 copies it beside jarvis_hud.py;
focus.patch adds the five routes; jarvis_quick.py answers the spoken and
typed commands without the AI model).

THE OWNER'S DECISION (2026-09-25, CLAUDE.md, after the "Build Your Own
Jarvis" prompt pack): "Focus sessions, off unless started: a timer plus
Quiet; Jarvis watches which app/site is in front ON THE PC ONLY, names the
distraction out loud ('Instagram can wait') but never stores what it saw
(only counts), waits until the owner settles before locking on, and ends
with a report card. Snooze, 'I'm doing research', pause and stop by voice.
Nothing leaves the PC." And the creativity audit (usefulness.md idea 3):
Quiet during the session, back to Active at the end ONLY if focus set Quiet.

IN PLAIN WORDS, WHAT HAPPENS
  1. The owner says "focus for 30 minutes" (or presses Start in either app).
     Nothing is watched before that, and nothing after it ends.
  2. Jarvis goes Quiet (if it was Active) and sets ONE job on the one
     scheduler for the end (kind "focus", jarvis_schedule.register_kind).
  3. Once a second, it asks Windows which window is in front - fresh every
     time - and, for a web browser, which SITE the front tab is on (the host
     only, e.g. "youtube.com", never the address). That is "the reader".
  4. It waits for the owner to SETTLE: the same app (and site) in front for
     two looks in a row. Jarvis's own windows never count - they are home
     base. Then it locks on to that and says "Locked on."
  5. Leaving it for longer than the grace (0.8 s) is a drift. Jarvis names it
     out loud, from canned lines, never the AI model: "Instagram can wait."
     Lines get firmer with each drift (three tiers, four lines each), and it
     repeats every minute while one drift lasts.
  6. At the end it goes back to Active (only if focus set Quiet) and gives a
     report card: minutes on target out of the plan, drifts, and a streak.

THE PRIVACY LAW - enforced by the shape of the code, and tested
  * WHAT IT SAW IS NEVER KEPT. The reader turns the program name and the
    site into two salted fingerprints (HMAC-SHA256 with a random key made
    fresh for each session, held in memory, never written). Fingerprints are
    compared and thrown away. The key dies with the session, so even a
    fingerprint that lingered in memory could not be matched to a name.
  * THE NAME RIDES ONE TICK. The spoken name ("Instagram") is made by the
    reader for the look it came from. If that look causes a callout, the name
    goes into that one sentence, which waits at most CALLOUT_TTL_S seconds
    for the desktop to fetch it (once - it is erased when read) and is then
    gone. It is never in the state the apps read, the report card, the
    ledger, the audit log, an event, the chat history or a note.
  * WHAT THE APPS SEE is a whitelist of booleans and counters (`status()`,
    `diag()`); the ledger file holds numbers and true/false ONLY - its writer
    turns every value into a number, so it cannot hold a word.
    backend/test_focus.py drives a drift with a made-up program and site name
    nobody would write in canned text and proves the names appear in the
    spoken line and NOWHERE else.
  * NOTHING LEAVES THE PC. The spoken line is fetched only from this PC
    (`GET /api/focus/callout` refuses any other address), and the phone sees
    the countdown and the counts - never what was in front.
  * IT NEVER TURNS A MICROPHONE ON. It only speaks, through the desktop app's
    own speaker, and only while a session the owner started is running.

WHY THERE IS NO APPROVAL CARD
Reading what is on screen normally sits under the computer-control rules:
there, READING a window's contents is `jarvis_ui_control_plan`, tier "auto"
(read-only, harmless - ui-control-wiring.patch), and only ACTING
(`control_computer`) asks. A focus session reads less than that plan step
does (the front window's program and a site name, not its controls), sends
no input, keeps nothing but counts, is local, and exists only because the
owner asked for it that moment. Going Quiet is `power_manage` (auto, "the
safe direction either way"). So it starts at once, with no card - and if the
owner has set `power_manage` to "ask", the Quiet part raises that card as
usual; the session runs either way.

THE TIMER IS ON THE ONE SCHEDULER (ARCHITECTURE section 12)
The end of a session is one job of kind "focus" on jarvis_schedule. The
one-second look is not a clock: it is a sensor that exists only while a
session runs, and it stops when the session does. If the scheduler cannot
take the job, the look ends the session at its time instead, and the status
says so (`timer_on_scheduler: false`). The job is not listed in Coming up
(its own panel shows the countdown) and tells nobody when it goes off (the
`focus` event does). A backend restart forgets the session (it is in memory
on purpose); the job then goes off later and does nothing.

QUIET, AND BACK
Started while Active: Quiet, recorded by jarvis_power as WHY. At the end:
Active again, but only if jarvis_power still says focus set it (the owner
choosing another mode meanwhile wins). Started while Quiet or on Standby:
left as it is. The callouts still speak during Quiet: they are the thing the
owner asked for, not something Jarvis started on its own.

THE WORDS
Every sentence here is canned: no AI model is involved anywhere. The warm
lines are the default; MANNER_SOURCE / manner() is the hook for the owner's
"warm / plain" setting (the owner's decision of 2026-09-25) - plain lines are
businesslike. Not wired yet: that setting was built at the same time.

KNOBS
Every number is a named constant just below. Tune them from what the owner
measures on the PC (`GET /api/focus/diag`), not from memory.

WHAT WAS VERIFIED, AND WHAT WAS NOT (said plainly)
Verified here: everything with a stand-in reader (backend/test_focus.py).
NOT verified - no Windows in this container: the Windows reader below.
  * The front window's program: GetForegroundWindow ->
    GetWindowThreadProcessId -> QueryFullProcessImageNameW (ctypes, no
    package). Documented Windows calls; believed reliable. Store apps
    (ApplicationFrameHost.exe) are looked through to the app inside.
  * The front tab's SITE: UI Automation (the `uiautomation` package already
    listed for jarvis_ui_control.py). It finds the address box of Chrome,
    Edge, Brave, Vivaldi, Opera (an Edit control inside a toolbar) or
    Firefox (AutomationId "urlbar-input") and reads its value - the page's
    address, which is cut down to the host right there and never kept. This
    is ASSUMED from how those browsers expose their toolbars; it must be
    tried on the owner's PC. When it cannot be read (the package is missing,
    a browser that hides its toolbar, the owner typing in the address box),
    the lock falls back to the browser app alone after APP_ONLY_AFTER_S, and
    says so out loud.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import ntpath
import os
import re
import secrets
import threading
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

try:
    import jarvis_framework as fw
except Exception:  # pragma: no cover - shipped beside it on the PC
    fw = None  # type: ignore

# --------------------------------------------------------------------------
#   Knobs - every one a named constant, tuned from the diag, not from memory
# --------------------------------------------------------------------------

#: How often the front window is read, in seconds.
TICK_S = 1.0
#: How long a switch away may last before it is a drift. With a one-second
#: look this means "still away at the next look".
GRACE_S = 0.8
#: The same app (and site) in front for this many looks in a row = settled.
SETTLE_TICKS = 2
#: Settled in a browser whose site cannot be read: lock on the browser alone
#: after this long, rather than never. A wrong lock is worse than none, so it
#: never guesses a site.
APP_ONLY_AFTER_S = 45.0
#: While one drift lasts, say something again this often ("nag").
NAG_EVERY_S = 60.0
NAG_MIN_S = 20.0
NAG_MAX_S = 600.0
#: "Snooze": no callouts for this long (drifts still count).
SNOOZE_S = 5 * 60.0
SNOOZE_MAX_S = 30 * 60.0
#: "I need a minute": no callouts for this long.
RELIEF_S = 3 * 60.0
#: "I'm doing research" said just after the drift ended (typing it into
#: Jarvis brings Jarvis to the front, which ends the drift) still refunds it.
EXCUSE_WINDOW_S = 90.0
#: Session length, in minutes.
DEFAULT_MINUTES = 25
MIN_MINUTES = 1
MAX_MINUTES = 240
EXTEND_DEFAULT_MIN = 10
#: A session is clean at this many percent on target, run to the end.
CLEAN_PCT = 85
#: A spoken line waits this long for the desktop to fetch it, then is erased.
CALLOUT_TTL_S = 8.0
#: A gap between looks longer than this (the PC slept) counts as this much.
MAX_DT_S = 2.5
#: Sessions kept in the ledger (numbers only).
LEDGER_KEEP = 200
#: The owner's "on what" words, at most this long.
MAX_INTENT = 60
#: Naming the distraction out loud. False: the nameless lines are used.
NAMING = True

#: The scheduler kind for the end of a session.
KIND = "focus"
#: What jarvis_power records as the reason for Quiet (and for Active again).
WHY = "the focus session"

# --------------------------------------------------------------------------
#   The words - canned, never the AI model
# --------------------------------------------------------------------------

TITLE = "Focus session"
DETAIL = ("A timer plus Quiet. On the PC, Jarvis watches which app or site is in front "
          "and says so when you drift - out loud, on the PC only. It keeps counts, never "
          "what it saw, and nothing leaves the PC. Off unless you start it.")
PHONE_NOTE = ("Watching what is in front happens on the PC only; this phone shows the "
              "countdown and the counts.")
MISSING = "Your PC's Jarvis does not have focus sessions yet - run apply-patches.ps1 on the PC."

LOCKED_LINE = "Locked on."
LOCKED_APP_ONLY_LINE = ("Locked on the browser as a whole - I could not read which site, so "
                        "any site in it counts.")
REARM_LINE = "Go to it - I'll lock on where you land."

#: Three tiers, four lines each, {name} filled from the look that drifted.
WARM_NAMED = (
    ("{name} can wait.",
     "{name}? That can wait until the timer's done.",
     "Back to it - {name} will still be there later.",
     "{name} isn't what we're doing right now."),
    ("{name} again. Back to the work.",
     "That's twice into {name}. Back to it.",
     "{name} keeps calling. Don't answer.",
     "Another trip to {name}. The work is waiting."),
    ("{name} is becoming the project. Back to the real one.",
     "In {name} again. The session is slipping away.",
     "{name} is winning this one. Take the time back.",
     "We keep ending up in {name}. Close it and carry on."),
)
WARM_NAMELESS = (
    ("That can wait.",
     "Back to what you were doing.",
     "That's not what we're focusing on.",
     "Let's get back to it."),
    ("Drifting again. Back to it.",
     "That's twice now. Back to the work.",
     "The work is waiting.",
     "Off course again - back you go."),
    ("The detours are becoming the project.",
     "That's a lot of wandering. Back to it.",
     "The session is slipping away.",
     "Close it and carry on."),
)
#: The first callout of a session, when the owner said what they are on.
WARM_FIRST_WITH_INTENT = "{name} doesn't look like {intent} to me."
PLAIN_NAMED = (
    ("Off target: {name}.",
     "{name} is not part of this session.",
     "Back to the task, please. {name} is in front.",
     "{name} is off target."),
    ("Off target again: {name}.",
     "Second drift: {name}.",
     "{name} again. Back to the task.",
     "Off target: {name}, again."),
    ("Repeated drift: {name}.",
     "{name}, again. The session is running.",
     "Still off target: {name}.",
     "Drifting to {name} again. Back to the task."),
)
PLAIN_NAMELESS = (
    ("Off target.", "That is not part of this session.", "Back to the task, please.",
     "Off target - back to the task."),
    ("Off target again.", "Second drift.", "Back to the task.", "Off target, again."),
    ("Repeated drift.", "Still off target.", "The session is running.",
     "Drifting again. Back to the task."),
)


#: MERGE HOOK for the owner's manner setting ("warm and brief by default,
#: with a Plain option", decided 2026-09-25; manner changes only how Jarvis
#: phrases things). That setting was being built at the same time as this
#: file, so nothing is wired here yet: set this to a function that answers
#: "warm" or "plain" when the two land together. Until then: warm.
MANNER_SOURCE: Optional[Callable[[], str]] = None


def manner() -> str:
    """"warm" (the default) or "plain". Anything unreadable is "warm"."""
    if MANNER_SOURCE is None:
        return "warm"
    try:
        return "plain" if str(MANNER_SOURCE() or "").strip().lower() == "plain" else "warm"
    except Exception:
        return "warm"


# --------------------------------------------------------------------------
#   Names for what is in front - used for ONE spoken line, stored nowhere
# --------------------------------------------------------------------------

#: The big sites, by host or by registrable domain.
SITE_NAMES = {
    "instagram.com": "Instagram", "youtube.com": "YouTube", "youtu.be": "YouTube",
    "x.com": "X", "twitter.com": "X", "reddit.com": "Reddit", "tiktok.com": "TikTok",
    "netflix.com": "Netflix", "facebook.com": "Facebook", "mail.google.com": "Gmail",
    "twitch.tv": "Twitch", "linkedin.com": "LinkedIn", "news.ycombinator.com": "Hacker News",
    "discord.com": "Discord", "web.whatsapp.com": "WhatsApp", "amazon.com": "Amazon",
    "amazon.co.uk": "Amazon", "ebay.com": "eBay", "ebay.co.uk": "eBay",
    "primevideo.com": "Prime Video", "disneyplus.com": "Disney Plus", "bbc.co.uk": "the BBC",
    "pinterest.com": "Pinterest", "tumblr.com": "Tumblr", "spotify.com": "Spotify",
}
#: Program file names -> the name said out loud. Anything else: the file
#: name without ".exe".
APP_NAMES = {
    "slack.exe": "Slack", "discord.exe": "Discord", "spotify.exe": "Spotify",
    "steam.exe": "Steam", "steamwebhelper.exe": "Steam", "whatsapp.exe": "WhatsApp",
    "telegram.exe": "Telegram", "teams.exe": "Teams", "ms-teams.exe": "Teams",
    "outlook.exe": "Outlook", "olk.exe": "Outlook", "thunderbird.exe": "Thunderbird",
    "netflix.exe": "Netflix", "epicgameslauncher.exe": "the Epic Games launcher",
    "battle.net.exe": "Battle.net", "signal.exe": "Signal", "messenger.exe": "Messenger",
    "chrome.exe": "Chrome", "msedge.exe": "Edge", "firefox.exe": "Firefox",
    "brave.exe": "Brave", "vivaldi.exe": "Vivaldi", "opera.exe": "Opera",
}
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


def site_name(host: str) -> str:
    """The name said out loud for a site: a big site's own name, else the
    bare domain ("example.com")."""
    s = site_of(host)
    if not s:
        return ""
    if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", s) or s == "localhost":
        return "that local page"
    return SITE_NAMES.get(s) or SITE_NAMES.get(_registrable(s)) or _registrable(s)


def app_name(exe: str) -> str:
    """The name said out loud for a program."""
    e = ntpath.basename(str(exe or "")).lower()
    if e in APP_NAMES:
        return APP_NAMES[e]
    stem = e[:-4] if e.endswith(".exe") else e
    stem = re.sub(r"[_\-]+", " ", stem).strip()
    return (stem[:1].upper() + stem[1:]) if stem else "that"


# --------------------------------------------------------------------------
#   The reader - identities are compared and thrown away in here
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Look:
    """What one look at the front window gives the engine: booleans, two
    salted fingerprints, and - for this tick only - the name to say. The
    engine keeps the booleans for the diag and drops the rest at the end
    of the tick. `say_as` must never be copied anywhere but into one line."""
    readable: bool
    neutral: bool = False
    jarvis: bool = False
    browser: bool = False
    host_read: bool = False
    app_key: str = ""
    site_key: str = ""
    say_as: str = ""

    def flags(self) -> dict:
        return {"readable": self.readable, "neutral": self.neutral, "jarvis": self.jarvis,
                "browser": self.browser, "host_read": self.host_read}


def _key(salt: bytes, kind: str, value: str) -> str:
    return hmac.new(salt, (kind + "\0" + value).encode("utf-8"), hashlib.sha256).hexdigest()


def _is_jarvis_title(title: str) -> bool:
    try:
        import jarvis_ui_control
        return bool(jarvis_ui_control.is_jarvis_window(title))
    except Exception:
        return re.match(r"jarvis(?![\w'])", " ".join(str(title or "").split()), re.I) is not None


def look_from(raw: Optional[dict], salt: bytes) -> Look:
    """Turn one raw reading - {"exe", "title", "cls", "host"} from the probe -
    into a Look. The raw reading is not kept: the program name and the site
    become fingerprints under this session's salt, and the name to say."""
    if not isinstance(raw, dict):
        return Look(readable=False)
    exe = ntpath.basename(str(raw.get("exe") or "")).lower()
    cls = str(raw.get("cls") or "")
    if not exe:
        return Look(readable=False)
    if cls in NEUTRAL_CLASSES or exe in NEUTRAL_EXES:
        return Look(readable=True, neutral=True)
    if exe in JARVIS_EXES or _is_jarvis_title(str(raw.get("title") or "")):
        return Look(readable=True, jarvis=True)
    browser = exe in BROWSERS
    host = host_of(raw.get("host") or "") if browser else ""
    site = site_of(host)
    return Look(readable=True, browser=browser, host_read=bool(site),
                app_key=_key(salt, "app", exe),
                site_key=_key(salt, "site", site) if site else "",
                say_as=(site_name(host) if site else app_name(exe)))


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
        try:
            p = c.GetValuePattern()
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


# --------------------------------------------------------------------------
#   The ledger - numbers and true/false ONLY
# --------------------------------------------------------------------------

LEDGER_KEYS = ("at", "planned_min", "active_min", "on_target_min", "adrift_min",
               "excused_min", "drifts", "percent", "completed", "clean")
_BOOL_KEYS = ("completed", "clean")


def _config_dir() -> Path:
    try:
        import jarvis_schedule
        return jarvis_schedule._config_dir()
    except Exception:
        return Path(os.environ.get("OPENJARVIS_CONFIG_DIR") or
                    Path.home() / ".openjarvis")


def ledger_path() -> Path:
    env = os.environ.get("JARVIS_FOCUS_LEDGER")
    return Path(env) if env else _config_dir() / "focus_ledger.json"


def ledger_row(d: dict) -> dict:
    """ONE row, as it may be stored: the whitelisted keys only, each turned
    into a number or true/false. A word cannot survive this."""
    out = {}
    for k in LEDGER_KEYS:
        v = d.get(k)
        if k in _BOOL_KEYS:
            out[k] = bool(v)
        elif v is None:
            out[k] = -1 if k == "percent" else 0
        else:
            try:
                out[k] = int(round(float(v)))
            except (TypeError, ValueError):
                out[k] = 0
    return out


def read_ledger(path: Optional[Path] = None) -> list:
    p = path or ledger_path()
    try:
        rows = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []
    return [ledger_row(r) for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def write_ledger(rows: list, path: Optional[Path] = None) -> None:
    p = path or ledger_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    clean = [ledger_row(r) for r in rows][-LEDGER_KEEP:]
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(clean, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, p)


def streak_of(rows: list) -> int:
    n = 0
    for r in reversed(rows):
        if not r.get("clean"):
            break
        n += 1
    return n


# --------------------------------------------------------------------------
#   Words for numbers
# --------------------------------------------------------------------------

def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def left_words(seconds: float) -> str:
    s = max(0, int(round(seconds)))
    if s < 60:
        return _plural(s, "second", "seconds")
    m = (s + 30) // 60
    if m < 60:
        return _plural(m, "minute", "minutes")
    h, mm = divmod(m, 60)
    return _plural(h, "hour", "hours") + (f" {_plural(mm, 'minute', 'minutes')}" if mm else "")


def report_from(row: dict, streak: int) -> dict:
    """The report card - built from a ledger row, so it can only say numbers."""
    r = ledger_row(row)
    done = r["completed"]
    title = "Focus session done." if done else "Focus session stopped early."
    on, planned, active = r["on_target_min"], r["planned_min"], r["active_min"]
    lines = [f"On target: {on} of {_plural(planned, 'minute', 'minutes')}." if done else
             f"On target: {on} of {_plural(active, 'minute', 'minutes')} ({planned} planned)."]
    d, adrift = r["drifts"], r["adrift_min"]
    if d == 0:
        lines.append("No drifts.")
    else:
        lines.append(f"Drifted {'once' if d == 1 else f'{d} times'}, "
                     f"{_plural(adrift, 'minute', 'minutes')} in all.")
    if r["excused_min"] > 0:
        lines.append(f"Research: {_plural(r['excused_min'], 'minute', 'minutes')}, "
                     f"not counted against you.")
    if r["percent"] < 0:
        lines.append("Jarvis never locked on, so there is no score.")
    else:
        lines.append(f"{r['percent']}% focused.")
    if r["clean"]:
        lines.append(f"Streak: {_plural(streak, 'clean session', 'clean sessions')} in a row.")
    else:
        lines.append(f"The streak starts again: a clean session is {CLEAN_PCT}% or more, "
                     f"run to the end.")
    drift_said = "no drifts" if d == 0 else ("one drift" if d == 1 else f"{d} drifts")
    spoken = (f"{title} {on} of {_plural(planned if done else active, 'minute', 'minutes')} "
              f"on target, {drift_said}."
              + (f" Streak: {streak}." if r["clean"] else ""))
    return {"completed": done, "planned_min": planned, "active_min": active,
            "on_target_min": on, "adrift_min": adrift, "excused_min": r["excused_min"],
            "drifts": d, "percent": (None if r["percent"] < 0 else r["percent"]),
            "clean": r["clean"], "streak": streak, "at": r["at"],
            "title": title, "lines": lines, "spoken": spoken}


# --------------------------------------------------------------------------
#   The engine
# --------------------------------------------------------------------------

def _default_publish(kind: str, data: dict) -> None:
    try:
        import jarvis_events
        jarvis_events.BUS.publish(kind, data)
    except Exception:
        pass


def _default_audit(event: str, detail: dict) -> None:
    # Outcomes and counts. Never a name, never a title, never a site.
    try:
        if fw is not None:
            fw.audit_log(event, detail)
    except Exception:
        pass


def _default_sched():
    import jarvis_schedule
    return jarvis_schedule.get()


def _default_power():
    import jarvis_power
    return jarvis_power


def _default_switch():
    import jarvis_power_switch
    return jarvis_power_switch


class Engine:
    """One focus session at a time. Everything replaceable for the tests:
    the clock, the probe, the scheduler, power, the bus, the audit log, the
    ledger file, the manner, and whether a look thread is started."""

    def __init__(self, *, clock: Callable[[], float] = time.time,
                 probe: Optional[Callable[[], Optional[dict]]] = None,
                 sched: Optional[Callable[[], object]] = None,
                 power: Optional[Callable[[], object]] = None,
                 switch: Optional[Callable[[], object]] = None,
                 publish: Callable[[str, dict], None] = _default_publish,
                 audit: Callable[[str, dict], None] = _default_audit,
                 ledger: Optional[Path] = None,
                 manner_of: Callable[[], str] = manner,
                 threads: bool = True):
        self.clock = clock
        self.probe = probe or windows_probe
        self._sched = sched or _default_sched
        self._power = power or _default_power
        self._switch = switch or _default_switch
        self.publish = publish
        self.audit = audit
        self.ledger = ledger
        self.manner_of = manner_of
        self.threads = threads
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._stop.set()
        self._thread: Optional[threading.Thread] = None
        self._seq = 0
        self._mail: Optional[tuple] = None          # (seq, line, at)
        self._report: Optional[dict] = None
        self._reset()

    # ---- state -------------------------------------------------------------------

    def _reset(self) -> None:
        self.on = False
        self.paused = False
        self.started_at = 0.0
        self.ends_at = 0.0
        self.left_at_pause = 0.0
        self.planned_s = 0.0
        self.job_id = ""
        self.on_scheduler = False
        self.intent = ""
        self._salt = b""
        self._t_app = ""
        self._t_site = ""
        self.lock_kind = ""
        self.deferred = False
        self._c_app = ""
        self._c_site = ""
        self._c_browser = False
        self._c_hostless = False
        self.settle = 0
        self._c_since = 0.0
        self.drifting = False
        self.drift_since = 0.0
        self.drift_counted = False
        self.drift_callouts = 0
        self.excursion_s = 0.0
        self._last_exc: Optional[dict] = None
        self.excused = False
        self.excused_off = False
        self.excused_at = 0.0
        self.quiet_until = 0.0
        self.nag_every = NAG_EVERY_S
        self.last_callout = 0.0
        self.on_target_s = 0.0
        self.adrift_s = 0.0
        self.excused_s = 0.0
        self.home_s = 0.0
        self.settling_s = 0.0
        self.drifts = 0
        self.called = 0
        self.first_done = False
        self.set_quiet = False
        self.front: dict = {}
        self.on_target: Optional[bool] = None
        self.last_tick = 0.0
        self._rot = [secrets.randbelow(4) for _ in range(3)]

    def is_on(self) -> bool:
        return self.on

    def now(self) -> float:
        return float(self.clock())

    def left_s(self, now: Optional[float] = None) -> float:
        now = self.now() if now is None else now
        if not self.on:
            return 0.0
        return max(0.0, self.left_at_pause if self.paused else self.ends_at - now)

    # ---- speaking: one line, fetched once by the desktop, then gone --------------

    def _speak(self, line: str) -> None:
        with self._lock:
            self._seq += 1
            self._mail = (self._seq, line, self.now())
            seq = self._seq
        self.publish("focus", {"state": "callout", "seq": seq})

    def take_line(self, seq) -> Optional[str]:
        """The waiting line, ONCE - erased as it is read. None when there is
        none, it is not that one, or it waited longer than CALLOUT_TTL_S."""
        with self._lock:
            m = self._mail
            if m is None:
                return None
            if self.now() - m[2] > CALLOUT_TTL_S:
                self._mail = None
                return None
            try:
                wanted = int(seq)
            except (TypeError, ValueError):
                return None
            if wanted != m[0]:
                return None
            self._mail = None
            return m[1]

    def _expire_mail(self, now: float) -> None:
        if self._mail is not None and now - self._mail[2] > CALLOUT_TTL_S:
            self._mail = None

    def waiting_line(self) -> bool:
        return self._mail is not None

    # ---- start and the timer ------------------------------------------------------

    def start(self, minutes=None, intent: str = "", by: str = "") -> tuple:
        """(code, answer). 409 while a session runs."""
        try:
            minutes = float(DEFAULT_MINUTES if minutes in (None, "") else minutes)
        except (TypeError, ValueError):
            return 400, {"ok": False, "error": "How many minutes? (a number)"}
        if minutes != minutes or minutes < MIN_MINUTES or minutes > MAX_MINUTES:
            return 400, {"ok": False, "error": f"A focus session is {MIN_MINUTES} to "
                                               f"{MAX_MINUTES} minutes long."}
        intent = " ".join(str(intent or "").split())[:MAX_INTENT]
        with self._lock:
            if self.on:
                return 409, {"ok": False, "error": (
                    f"A focus session is already running - {left_words(self.left_s())} "
                    f"left. Stop it first, or extend it."), "focus": self._status_locked()}
            now = self.now()
            self._reset()
            self.on = True
            self.started_at = now
            self.planned_s = minutes * 60.0
            self.ends_at = now + self.planned_s
            self.intent = intent
            self._salt = secrets.token_bytes(32)
            self.deferred = True
            self.last_tick = now
            self._report = None
        self._set_timer()
        quiet = self._go_quiet(by)
        self.audit("focus.start", {"minutes": int(round(minutes)), "by": by or "an app",
                                   "quiet": quiet, "on_scheduler": self.on_scheduler})
        self.publish("focus", {"state": "started"})
        if self.threads:
            self._start_thread()
        mins = int(round(minutes))
        said = f"Focus for {_plural(mins, 'minute', 'minutes')}"
        said += f", on {intent}." if intent else "."
        if quiet == "set":
            said += " Jarvis is on Quiet until it ends."
        elif quiet == "asking":
            said += " Your power setting asks first, so a card to go Quiet is on your PC."
        said += (" Go to what you're working on - I'll lock on there once you settle.")
        return 200, {"ok": True, "said": said, "focus": self.status()}

    def _set_timer(self) -> None:
        try:
            s = self._sched()
            job = s.add_at(KIND, self.ends_at, "", source="focus")
            self.job_id = str(job["id"])
            self.on_scheduler = True
        except Exception:
            self.job_id = ""
            self.on_scheduler = False

    def _drop_timer(self) -> None:
        jid, self.job_id = self.job_id, ""
        if not jid:
            return
        try:
            self._sched().act(jid, "delete")
        except Exception:
            pass

    def on_fire(self, job_id: str) -> None:
        """The scheduler's end-of-session job went off."""
        with self._lock:
            mine = self.on and not self.paused and job_id and job_id == self.job_id
        if mine:
            self.job_id = ""
            self.finish(completed=True, speak=True)

    # ---- Quiet, and back ------------------------------------------------------------

    def _go_quiet(self, by: str) -> str:
        """"set", "asking" (a power card is up), "kept" (was not Active) or
        "failed". Never raises."""
        try:
            power = self._power()
            if str(power.current()) != "active":
                return "kept"
            code, out = self._switch().set_mode("quiet", by=by or WHY, why=WHY, wait_s=1.5)
        except Exception:
            return "failed"
        if code == 200 and (out or {}).get("changed"):
            self.set_quiet = True
            return "set"
        if code == 202:
            self.set_quiet = True       # if it is approved, jarvis_power says WHY
            return "asking"
        return "failed"

    def _restore_power(self) -> str:
        """Back to Active only if focus set Quiet and nothing changed it
        since (jarvis_power.status()["why"] is still WHY)."""
        if not self.set_quiet:
            return "not ours"
        try:
            power = self._power()
            st = power.status() or {}
            if str(st.get("why") or "") != WHY or str(power.current()) != "quiet":
                return "changed since"
            code, out = self._switch().set_mode("active", by=WHY, why=WHY, wait_s=1.5)
        except Exception:
            return "failed"
        return "active" if code == 200 else "failed"

    # ---- the look ---------------------------------------------------------------------

    def _start_thread(self) -> None:
        # One stop signal per session: a look thread from a session that just
        # ended can never keep ticking into the next one.
        stop = threading.Event()
        self._stop = stop
        t = threading.Thread(target=self._run, args=(stop,), name="jarvis-focus-look",
                             daemon=True)
        self._thread = t
        t.start()

    def _run(self, stop: threading.Event) -> None:
        with _thread_context():
            while not stop.wait(TICK_S):
                if not self.on:
                    break
                try:
                    self.tick()
                except Exception:
                    pass

    def thread_alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def tick(self, now: Optional[float] = None) -> None:
        """One look. Public so the tests drive it with their own clock."""
        now = self.now() if now is None else now
        with self._lock:
            self._expire_mail(now)
            if not self.on:
                return
            dt = min(MAX_DT_S, max(0.0, now - self.last_tick))
            self.last_tick = now
            if self.paused:
                return
            if not self.on_scheduler and now >= self.ends_at:
                backstop = True
            else:
                backstop = False
        if backstop:
            self.finish(completed=True, speak=True)
            return
        try:
            raw = self.probe()
        except Exception:
            raw = None
        look = look_from(raw, self._salt)
        raw = None
        line = self._judge(look, now, dt)
        # The look (and the name in it) ends here.
        del look
        if line:
            self._speak(line)

    def _judge(self, look: Look, now: float, dt: float) -> str:
        """Everything a look changes. Returns a line to say, or ""."""
        with self._lock:
            self.front = look.flags()
            if not look.readable or look.neutral:
                self.on_target = None
                return ""
            if look.jarvis:
                # Home base: talking to Jarvis is never a drift. It does not
                # end one either - asking Jarvis something in the middle of a
                # trip to YouTube and going back there is still one drift -
                # and it is never counted as time adrift.
                self.home_s += dt
                self.on_target = None
                return ""
            if self.deferred:
                return self._settle(look, now, dt)
            return self._watch(look, now, dt)

    def _settle(self, look: Look, now: float, dt: float) -> str:
        self.settling_s += dt
        same = (look.app_key == self._c_app and
                (look.site_key == self._c_site if look.host_read else self._c_hostless))
        if not same:
            self._c_app, self._c_site = look.app_key, look.site_key
            self._c_browser, self._c_hostless = look.browser, not look.host_read
            self.settle = 1
            self._c_since = now
        else:
            self.settle += 1
        if self.settle < SETTLE_TICKS:
            return ""
        if look.browser and not look.host_read:
            if now - self._c_since < APP_ONLY_AFTER_S:
                return ""
            self._lock_on(look.app_key, "", "app")
            return LOCKED_APP_ONLY_LINE
        self._lock_on(look.app_key, look.site_key if look.browser else "",
                      "app_and_site" if look.browser else "app")
        return LOCKED_LINE

    def _lock_on(self, app: str, site: str, kind: str) -> None:
        self._t_app, self._t_site, self.lock_kind = app, site, kind
        self.deferred = False
        self.settle = 0
        self._c_app = self._c_site = ""
        self.on_target = True
        self.audit("focus.locked", {"lock": kind})
        self.publish("focus", {"state": "changed"})

    def _matches(self, look: Look) -> Optional[bool]:
        """True on target, False off, None when it cannot be told (the
        browser that is the target, with its site unreadable this look)."""
        if not hmac.compare_digest(look.app_key, self._t_app):
            return False
        if not self._t_site:
            return True
        if not look.host_read:
            return None
        return hmac.compare_digest(look.site_key, self._t_site)

    def _watch(self, look: Look, now: float, dt: float) -> str:
        hit = self._matches(look)
        if hit is None:
            return ""
        self.on_target = hit
        if hit:
            self.on_target_s += dt
            if self.excused and (self.excused_off or now - self.excused_at > EXCUSE_WINDOW_S):
                # Back on it after the research (or an excuse said in advance
                # that went unused): the next trip counts again.
                self.excused = False
            self._end_drift(now)
            return ""
        if not self.drifting:
            self.drifting = True
            self.drift_since = now
            self.drift_counted = False
            self.drift_callouts = 0
            self.excursion_s = 0.0
            self.publish("focus", {"state": "changed"})
        if self.excused:
            self.excused_off = True
            self.excused_s += dt
            return ""
        if not self.drift_counted:
            if now - self.drift_since < GRACE_S:
                return ""
            self.drift_counted = True
            self.drifts += 1
        self.adrift_s += dt
        self.excursion_s += dt
        if now < self.quiet_until:
            return ""
        if self.drift_callouts and now - self.last_callout < self.nag_every:
            return ""
        return self._callout(look, now)

    def _end_drift(self, now: float) -> None:
        if not self.drifting:
            return
        self._last_exc = {"ended": now, "s": self.excursion_s, "counted": self.drift_counted,
                          "refunded": self.excused}
        self.drifting = False
        self.drift_counted = False
        self.drift_callouts = 0
        self.excursion_s = 0.0
        self.publish("focus", {"state": "changed"})

    def _callout(self, look: Look, now: float) -> str:
        if self.drift_callouts == 0:
            self.called += 1
        tier = min(3, self.called + self.drift_callouts) - 1
        self.drift_callouts += 1
        self.last_callout = now
        plain = self.manner_of() == "plain"
        name = look.say_as if NAMING else ""
        if name and not self.first_done and self.intent and not plain:
            self.first_done = True
            return WARM_FIRST_WITH_INTENT.format(name=name, intent=self.intent)
        self.first_done = True
        pools = (PLAIN_NAMED if name else PLAIN_NAMELESS) if plain else \
            (WARM_NAMED if name else WARM_NAMELESS)
        pool = pools[tier]
        i = self._rot[tier]
        self._rot[tier] = (i + 1) % len(pool)
        line = pool[i % len(pool)]
        return line.format(name=name) if name else line

    # ---- the owner's commands -----------------------------------------------------------

    def _need_on(self) -> Optional[tuple]:
        if not self.on:
            return 409, {"ok": False, "error": "No focus session is running.",
                         "focus": self.status()}
        return None

    def act(self, do: str, minutes=None, by: str = "") -> tuple:
        do = str(do or "").strip().lower()
        fn = {"pause": self.pause, "resume": self.resume, "stop": self.stop,
              "extend": lambda: self.extend(minutes), "snooze": lambda: self.snooze(minutes),
              "research": self.excuse, "relief": self.relief, "lock": self.lock_on_this,
              "nag": lambda: self.nag(minutes)}.get(do)
        if fn is None:
            return 400, {"ok": False, "error": "do is one of: pause, resume, stop, extend, "
                                               "snooze, research, relief, lock, nag"}
        with self._lock:
            refused = self._need_on()
        if refused:
            return refused
        said = fn()
        self.audit("focus.act", {"do": do, "by": by or "an app"})
        return 200, {"ok": True, "said": said, "focus": self.status()}

    def pause(self) -> str:
        with self._lock:
            if self.paused:
                return f"Already paused, with {left_words(self.left_s())} left."
            now = self.now()
            self.left_at_pause = max(0.0, self.ends_at - now)
            self.paused = True
            self._end_drift(now)
            self.on_target = None
        self._drop_timer()
        self.publish("focus", {"state": "changed"})
        return (f"Paused with {left_words(self.left_at_pause)} left. Nothing is watched "
                f"until you resume.")

    def resume(self) -> str:
        with self._lock:
            if not self.paused:
                return "It isn't paused."
            now = self.now()
            self.ends_at = now + self.left_at_pause
            self.paused = False
            self.last_tick = now
        self._set_timer()
        self.publish("focus", {"state": "changed"})
        return f"Resumed - {left_words(self.left_s())} left."

    def extend(self, minutes=None) -> str:
        try:
            m = float(EXTEND_DEFAULT_MIN if minutes in (None, "") else minutes)
        except (TypeError, ValueError):
            return "By how many minutes?"
        with self._lock:
            total = (self.planned_s / 60.0) + m
            if m <= 0 or total > MAX_MINUTES:
                return f"A focus session can be up to {MAX_MINUTES} minutes long."
            self.planned_s += m * 60.0
            if self.paused:
                self.left_at_pause += m * 60.0
            else:
                self.ends_at += m * 60.0
            paused = self.paused
        if not paused:
            self._drop_timer()
            self._set_timer()
        self.publish("focus", {"state": "changed"})
        return f"Extended by {_plural(int(round(m)), 'minute', 'minutes')} - " \
               f"{left_words(self.left_s())} left."

    def snooze(self, minutes=None) -> str:
        try:
            s = SNOOZE_S if minutes in (None, "") else float(minutes) * 60.0
        except (TypeError, ValueError):
            s = SNOOZE_S
        s = max(10.0, min(SNOOZE_MAX_S, s))
        with self._lock:
            self.quiet_until = self.now() + s
        self.publish("focus", {"state": "changed"})
        return (f"Snoozed - no callouts for {left_words(s)}. Drifts still count.")

    def relief(self) -> str:
        with self._lock:
            self.quiet_until = max(self.quiet_until, self.now() + RELIEF_S)
        self.publish("focus", {"state": "changed"})
        return f"Of course - no nudges for {left_words(RELIEF_S)}."

    def nag(self, seconds=None) -> str:
        try:
            s = float(seconds)
        except (TypeError, ValueError):
            return "How often? Say, for example, every 30 seconds."
        s = max(NAG_MIN_S, min(NAG_MAX_S, s))
        with self._lock:
            self.nag_every = s
        return f"While you drift, I'll say something every {left_words(s)}."

    def _refund(self, s: float, counted: bool) -> None:
        self.adrift_s = max(0.0, self.adrift_s - s)
        self.excused_s += s
        if counted and self.drifts > 0:
            self.drifts -= 1

    def excuse(self) -> str:
        """"I'm doing research": the excursion now (or the one that just
        ended) is refunded, and nothing is said until back on target."""
        with self._lock:
            now = self.now()
            if self.drifting and not self.excused:
                self._refund(self.excursion_s, self.drift_counted)
                self.drift_counted = False
                self.excursion_s = 0.0
                said = "Research it is - that doesn't count. I'll stay quiet until you're back."
            elif (self._last_exc and not self._last_exc["refunded"]
                  and now - self._last_exc["ended"] <= EXCUSE_WINDOW_S):
                self._refund(self._last_exc["s"], self._last_exc["counted"])
                self._last_exc["refunded"] = True
                self.drifting = False
                said = ("Research it is - that last trip doesn't count, and I'll stay quiet "
                        "until you're back on it.")
            else:
                said = ("Research it is - the next trip away doesn't count, and I'll stay "
                        "quiet until you're back on it.")
            self.excused = True
            self.excused_off = self.drifting
            self.excused_at = now
        self.publish("focus", {"state": "changed"})
        return said

    def lock_on_this(self) -> str:
        """"Lock on this": what is in front now becomes the target - or, when
        Jarvis itself is in front (a button in its window, or typing to it),
        the lock waits for the owner to settle again."""
        try:
            raw = self.probe()
        except Exception:
            raw = None
        look = look_from(raw, self._salt)
        raw = None
        with self._lock:
            now = self.now()
            forgiven = False
            if self.drifting:
                self._refund(self.excursion_s, self.drift_counted)
                forgiven = True
                self.drifting = False
                self.drift_counted = False
                self.excursion_s = 0.0
            if not look.readable or look.neutral or look.jarvis:
                self._t_app = self._t_site = self.lock_kind = ""
                self.deferred = True
                self.settle = 0
                self._c_app = self._c_site = ""
                self._c_since = now
                self.on_target = None
                said = REARM_LINE
            elif look.browser and not look.host_read:
                self._lock_on(look.app_key, "", "app")
                said = LOCKED_APP_ONLY_LINE
            else:
                self._lock_on(look.app_key, look.site_key if look.browser else "",
                              "app_and_site" if look.browser else "app")
                said = LOCKED_LINE
            self.excused = False
            self.excused_off = False
        del look
        self.publish("focus", {"state": "changed"})
        if forgiven and said != REARM_LINE:
            return said + " That last trip doesn't count."
        return said

    def stop(self) -> str:
        # The answer carries the report card; the PC does not ALSO say it
        # (a spoken "stop focus" would otherwise hear it twice).
        rep = self.finish(completed=False, speak=False)
        return rep["spoken"] if rep else "No focus session is running."

    def stop_everything(self) -> None:
        """MERGE HOOK for the "stop everything" hotkey (being built at the same
        time as this file): pause the session and drop a line waiting to be
        said. Pausing, not ending, so nothing is lost - "resume focus" picks
        it up. Call this from the stop-all hook when it lands."""
        with self._lock:
            self._mail = None
            on, paused = self.on, self.paused
        if on and not paused:
            self.pause()

    def finish(self, completed: bool, speak: bool = True) -> Optional[dict]:
        with self._lock:
            if not self.on:
                return None
            now = self.now()
            if self.paused:
                active = self.planned_s - self.left_at_pause
            else:
                active = min(self.planned_s, now - self.started_at)
            tracked = self.on_target_s + self.adrift_s
            percent = round(100.0 * self.on_target_s / tracked) if tracked > 0 else None
            planned_min = round(self.planned_s / 60.0)
            row = ledger_row({
                "at": int(now // 60 * 60), "planned_min": planned_min,
                "active_min": round(max(0.0, active) / 60.0),
                "on_target_min": round(self.on_target_s / 60.0),
                "adrift_min": round(self.adrift_s / 60.0),
                "excused_min": round(self.excused_s / 60.0),
                "drifts": self.drifts, "percent": percent, "completed": completed,
                "clean": bool(completed and percent is not None and percent >= CLEAN_PCT),
            })
            self.on = False
            self.paused = False
            self._stop.set()
            self._salt = b""
            self._t_app = self._t_site = self._c_app = self._c_site = ""
            self.drifting = False
            self.on_target = None
            jid = self.job_id
        # Outside the lock: switching power waits for its answer.
        restore = self._restore_power()
        if not completed and jid:
            self._drop_timer()
        self.job_id = ""
        rows = read_ledger(self.ledger)
        rows.append(row)
        try:
            write_ledger(rows, self.ledger)
            streak = streak_of(rows)
        except Exception:
            streak = streak_of(rows)
        rep = report_from(row, streak)
        with self._lock:
            self._report = rep
        self.audit("focus.end", dict({k: row[k] for k in LEDGER_KEYS}, power=restore))
        self.publish("focus", {"state": "ended"})
        if speak:
            self._speak(rep["spoken"])
        return rep

    # ---- what the apps see -------------------------------------------------------------

    def _state_word(self) -> str:
        if not self.on:
            return "off"
        if self.paused:
            return "paused"
        return "settling" if self.deferred else "locked"

    def _line(self, now: float) -> str:
        if not self.on:
            return "No focus session."
        left = left_words(self.left_s(now))
        if self.paused:
            return f"Paused with {left} left."
        if self.deferred:
            return (f"{left} left. Go to what you're working on - Jarvis locks on once "
                    f"you settle.")
        if self.drifting and self.excused:
            return f"{left} left - research, not counted."
        if self.drifting:
            return f"{left} left - off target."
        if self.on_target:
            return f"{left} left - on target."
        return f"{left} left."

    def _status_locked(self) -> dict:
        now = self.now()
        quiet_left = max(0.0, self.quiet_until - now) if self.on else 0.0
        report = self._report
        rows = None
        if report is None:
            rows = read_ledger(self.ledger)
            if rows and not self.on:
                report = report_from(rows[-1], streak_of(rows))
        out = {
            "available": True, "title": TITLE, "detail": DETAIL, "phone_note": PHONE_NOTE,
            "on": self.on, "paused": self.paused, "state": self._state_word(),
            "minutes": int(round(self.planned_s / 60.0)) if self.on else 0,
            "left_s": int(round(self.left_s(now))),
            "ends_at": (self.ends_at if self.on and not self.paused else None),
            "intent": self.intent if self.on else "",
            "deferred": bool(self.on and self.deferred),
            "locked": bool(self.on and not self.deferred and bool(self._t_app)),
            "lock": self.lock_kind if self.on else "",
            "on_target": (self.on_target if self.on and not self.paused else None),
            "drifting": bool(self.on and self.drifting and not self.paused),
            "excused": bool(self.on and self.excused),
            # The running session's counts (the last one's are in `report`).
            "drifts": int(self.drifts) if self.on else 0,
            "on_target_s": int(self.on_target_s) if self.on else 0,
            "adrift_s": int(self.adrift_s) if self.on else 0,
            "excused_s": int(self.excused_s) if self.on else 0,
            "quiet_left_s": int(round(quiet_left)),
            "set_quiet": bool(self.set_quiet),
            "timer_on_scheduler": bool(self.on_scheduler),
            "watching": bool(self.on and not self.paused and probe_available()),
            "line": self._line(now),
            "note": (f"No callouts for {left_words(quiet_left)} - drifts still count."
                     if quiet_left > 0 else ""),
            "report": report,
            "streak": int(report["streak"]) if report else streak_of(rows or []),
        }
        return out

    def status(self) -> dict:
        with self._lock:
            return self._status_locked()

    def diag(self) -> dict:
        """Booleans and counts only - never what was in front. For "it locked
        the wrong thing" and "it didn't notice": read it from the RUNNING
        backend (GET /api/focus/diag)."""
        with self._lock:
            now = self.now()
            f = self.front or {}
            return {
                "available": True, "on": self.on, "paused": self.paused,
                "look_thread_alive": self.thread_alive(),
                "last_look_age_s": (round(now - self.last_tick, 1) if self.on else None),
                "reader_on_windows": probe_available(),
                "front_readable": bool(f.get("readable")),
                "front_neutral": bool(f.get("neutral")),
                "front_is_jarvis": bool(f.get("jarvis")),
                "front_is_browser": bool(f.get("browser")),
                "front_site_readable": bool(f.get("host_read")),
                "deferred": bool(self.on and self.deferred),
                "settle_ticks": int(self.settle),
                "has_app_target": bool(self._t_app),
                "has_site_target": bool(self._t_site),
                "on_target": self.on_target if self.on else None,
                "drifting": self.drifting, "drift_counted": self.drift_counted,
                "excused": self.excused, "quiet": now < self.quiet_until,
                "line_waiting": self._mail is not None,
                "timer_on_scheduler": self.on_scheduler,
                "set_quiet": self.set_quiet, "naming": NAMING,
                "manner": self.manner_of(),
                "knobs": {"tick_s": TICK_S, "grace_s": GRACE_S, "settle_ticks": SETTLE_TICKS,
                          "app_only_after_s": APP_ONLY_AFTER_S, "nag_every_s": self.nag_every,
                          "snooze_s": SNOOZE_S, "relief_s": RELIEF_S, "clean_pct": CLEAN_PCT},
            }


# --------------------------------------------------------------------------
#   The one engine this backend runs, and the scheduler kind
# --------------------------------------------------------------------------

ENGINE = Engine()


def is_on() -> bool:
    """For jarvis_quick: is a session running? In memory; reads nothing."""
    return ENGINE.on


def spoken_status(st: dict) -> str:
    """ "How am I doing?" - from the status the apps see (counts only)."""
    if not st.get("on"):
        rep = st.get("report")
        if rep:
            return "No focus session is running. The last one: " + " ".join(rep.get("lines") or [])
        return "No focus session is running."
    parts = [str(st.get("line") or "")]
    d = int(st.get("drifts") or 0)
    parts.append("No drifts so far." if d == 0 else
                 f"{'One drift' if d == 1 else f'{d} drifts'} so far.")
    if st.get("note"):
        parts.append(str(st["note"]))
    return " ".join(p for p in parts if p)


def _on_fire(job_id: str) -> None:
    ENGINE.on_fire(job_id)


try:
    import jarvis_schedule as _S
    _S.register_kind(KIND, "focus session", "Jarvis: your focus session is over.",
                     has_text=False, on_fire=_on_fire, owner_listed=False, notify=False)
except Exception:  # pragma: no cover - the scheduler ships beside it
    _S = None


# --------------------------------------------------------------------------
#   Routes (focus.patch)
# --------------------------------------------------------------------------

def handle_get() -> tuple:
    return 200, ENGINE.status()


def handle_diag() -> tuple:
    return 200, ENGINE.diag()


def handle_start(body, *, by: str = "") -> tuple:
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "need a JSON object"}
    return ENGINE.start(body.get("minutes"), str(body.get("on") or ""), by=by)


def handle_act(body, *, by: str = "") -> tuple:
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "need a JSON object"}
    return ENGINE.act(body.get("do"), body.get("minutes"), by=by)


def from_this_pc(peer) -> bool:
    """Loopback only. The spoken line is for this PC's speaker; any other
    address - the phone included - is refused."""
    p = str(peer or "").strip().lower()
    if p.startswith("::ffff:"):
        p = p[7:]
    return p in ("127.0.0.1", "::1", "localhost") or p.startswith("127.")


def handle_callout(query: str, peer) -> tuple:
    """GET /api/focus/callout?seq=N -> (code, body, content type). The line
    is taken (erased) and turned into sound on this PC; its words are not
    sent - only the sound, and only to this PC."""
    if not from_this_pc(peer):
        return 403, {"ok": False, "error": "the spoken line is for this PC only"}, None
    q = urllib.parse.parse_qs(str(query or ""))
    seq = (q.get("seq") or [""])[0]
    line = ENGINE.take_line(seq)
    if line is None:
        return 404, {"ok": False, "reason": "no_line",
                     "error": "nothing is waiting to be said (it was said, or it waited "
                              "too long)"}, None
    wav = speak_wav(line)
    line = None
    if wav is None:
        return 503, {"available": False, "error": "no voice is installed on this PC"}, None
    return 200, wav, "audio/wav"


def speak_wav(text: str) -> Optional[bytes]:
    """The sound for one line, through the voice Jarvis speaks in
    (jarvis_speech._synthesise - the same path as "One moment.": a custom
    voice first, then Kokoro). Nothing is remembered: unlike say(), no
    timing row, no "Jarvis just said" note, no question window opened -
    so the microphone is never opened because of a callout."""
    try:
        import jarvis_speech
        samples, rate, *_ = jarvis_speech._synthesise(text, start_better=False)
        if samples is None:
            return None
        return jarvis_speech._write_wav(samples, rate)
    except Exception:
        return None
