"""jarvis_media.py - "pause", "next song", "what's playing": play, pause,
next, previous and now-playing for whatever is playing on this PC (Spotify,
a browser tab, or any other app that reports to Windows' own media
controls), through Windows' GlobalSystemMediaTransportControlsSessionManager.

NEW MODULE, shipped whole. media.patch adds one call at start-up,
`install(Handler, ...)` (the same shape as jarvis_stop_all.py and
jarvis_documents.py), which answers GET /api/media and POST
/api/media/control. docs/JARVIS-API.md section (see backend/README.md
"Music and video control").

THE OWNER'S DECISION (CLAUDE.md, 2026-09-27, feasibility I91):
"Music/video control on the PC: no card, only from the owner's own words."
Read carefully, on purpose: not "a setting, off by default" (the "Lights,
plugs and fans" pattern) - CLAUDE.md gives this feature no on/off switch at
all, so none is built here. What "only from the owner's own words" buys:

  * THERE IS NO MODEL TOOL. jarvis_agent.py's tool loop never offers this,
    so the AI model cannot start, stop or skip anything on its own
    initiative, and outside text (a web page, an email, a note) can never
    reach it either - there is nothing in the tool loop for outside text
    to steer.
  * The owner's typed or said words are read by jarvis_quick.py's fast
    path (control() and now_playing() below), which answers WITHOUT the AI
    model, on both apps (both go through the same chat pipeline; see
    CLAUDE.md, "A client must not do speech-to-text" - so a spoken command
    from either app already arrives here as plain text, transcribed on
    this PC). That is also why every apps' desktop "typing directly into
    Rust" path was not built: both apps already reach this the same way
    everything else in jarvis_quick.py does, so a second, Rust-native
    implementation would be a second copy of the same logic for no gain -
    see backend/README.md's own note on this, and the report for this
    piece of work.
  * `/api/media` and `/api/media/control` below are for a small "Now
    playing" plate in either app (a play/pause/next/previous set of
    buttons calling this route directly, never going through chat) -
    PARITY, not a new permission: pressing a button is exactly as much
    "the owner's own words" as saying "pause" out loud, and the route
    itself never raises a card either.
  * NEVER a card, whatever the tier tables say: this module never imports
    jarvis_gate at all, so there is no action name to give a tier to and
    nothing here can be made to ask.

WHAT IT NEVER DOES
Seek, change the volume, change shuffle or repeat, open an app, or choose
WHICH app's session to control (it always asks Windows for "the current
session" - the one Windows itself judges most relevant right now, the same
one the hardware media keys on a keyboard would control). Titles and
artists are read only for "what's playing", never learned as a fact, and
never saved: `now_playing()` marks its own answer as having read OUTSIDE
TEXT (READ_MARK below), because whatever is playing put that title there,
not the owner - the same reasoning jarvis_briefing.py gives for a calendar
title or an email's From line.

WINDOWS-ONLY, AND GRACEFUL WITHOUT IT
The real work is Windows' Global System Media Transport Controls, reached
from Python through the `winrt-Windows.Media.Control` package (PyPI, MIT;
`winrt.windows.media.control`). It is Windows-only and is not installed in
this repository's dev container, so every call into it is behind a plain
`import` inside a function, never at module load: importing this module on
Linux, or on a Windows PC where the package is missing, always succeeds -
only calling control() or now_playing() then says plainly why it could not
reach Windows' media controls, the same shape every other optional tool in
this backend uses (jarvis_documents.py's MarkItDown, jarvis_ocr.py's
recognizer).

TESTED WITHOUT WINDOWS
Like every other module here, the real winrt calls are one replaceable
`Deps` field each (control/now_playing); test_media.py injects plain
functions and never imports winrt or opens a real session.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Callable, Optional
from urllib.parse import urlsplit

#: What jarvis_quick.py's "what's playing" answer marks the turn with -
#: OUTSIDE TEXT, because the title and artist came from whatever is
#: playing, not from the owner (jarvis_agent._TurnWatch.took_in's rule:
#: any non-empty `read` list means the turn read outside text).
READ_MARK = "media_now_playing"

PATH = "/api/media"
CONTROL_ROUTE = "/api/media/control"

_ACTIONS = ("play", "pause", "next", "previous")

_SAID = {
    "play": "Playing.",
    "pause": "Paused.",
    "next": "Skipped to the next.",
    "previous": "Back to the previous.",
}

#: Why a call did not work, in the owner's own words - never a stack trace,
#: never the exception's message (which could quote a file path).
_REASON_WORDS = {
    "not_installed": ("Jarvis could not reach Windows' media controls on this PC - "
                      "winrt-Windows.Media.Control is not installed (see backend/README.md, "
                      "\"Music and video control\")."),
    "not_windows": "Music and video control only works on Windows.",
    "nothing": "Nothing seems to be playing right now.",
    "refused": "Windows did not do that just now - try again in a moment.",
}
_UNKNOWN_REASON = "Jarvis could not do that just now."


# --------------------------------------------------------------------------
#   The real thing - Windows' own media controls, through winrt
# --------------------------------------------------------------------------

async def _session():
    """The session Windows itself judges "current" right now, or None. Its
    own import, so a PC without the package still imports this module."""
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as Manager,
    )
    manager = await Manager.request_async()
    return manager.get_current_session()


async def _control_async(action: str) -> dict:
    try:
        session = await _session()
    except ImportError:
        return {"ok": False, "reason": "not_installed"}
    if session is None:
        return {"ok": False, "reason": "nothing"}
    try:
        if action == "play":
            ok = await session.try_play_async()
        elif action == "pause":
            ok = await session.try_pause_async()
        elif action == "next":
            ok = await session.try_skip_next_async()
        else:
            ok = await session.try_skip_previous_async()
    except Exception as exc:
        return {"ok": False, "reason": type(exc).__name__}
    return {"ok": bool(ok)} if ok else {"ok": False, "reason": "refused"}


async def _now_playing_async() -> dict:
    try:
        session = await _session()
    except ImportError:
        return {"ok": False, "reason": "not_installed"}
    if session is None:
        return {"ok": True, "playing": False, "title": "", "artist": ""}
    try:
        info = await session.try_get_media_properties_async()
    except Exception as exc:
        return {"ok": False, "reason": type(exc).__name__}
    playing = True
    try:
        from winrt.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionPlaybackStatus as Status,
        )
        playing = session.get_playback_info().playback_status == Status.PLAYING
    except Exception:
        pass    # Playback status could not be read: assume playing, the common case.
    return {"ok": True, "playing": playing, "title": str(getattr(info, "title", "") or ""),
            "artist": str(getattr(info, "artist", "") or "")}


def _default_control(action: str) -> dict:
    import sys
    if sys.platform != "win32":
        return {"ok": False, "reason": "not_windows"}
    try:
        return asyncio.run(_control_async(action))
    except ImportError:
        return {"ok": False, "reason": "not_installed"}
    except Exception as exc:
        return {"ok": False, "reason": type(exc).__name__}


def _default_now_playing() -> dict:
    import sys
    if sys.platform != "win32":
        return {"ok": False, "reason": "not_windows"}
    try:
        return asyncio.run(_now_playing_async())
    except ImportError:
        return {"ok": False, "reason": "not_installed"}
    except Exception as exc:
        return {"ok": False, "reason": type(exc).__name__}


@dataclass
class Deps:
    #: (action) -> {"ok": bool, "reason"?: str}. None: the real winrt call.
    control: Callable[[str], dict] = _default_control
    #: () -> {"ok": bool, "playing"?: bool, "title"?: str, "artist"?: str,
    #: "reason"?: str}. None: the real winrt call.
    now_playing: Callable[[], dict] = _default_now_playing


DEPS = Deps()


def _clip(s: str, cap: int = 200) -> str:
    s = " ".join(str(s or "").split())
    return s if len(s) <= cap else s[:cap - 1].rstrip() + "…"


def control(action: str, *, deps: Optional[Deps] = None) -> dict:
    """Play, pause, next or previous. Never a card, never raises: always
    {"ok", "said"}."""
    deps = deps or DEPS
    action = str(action or "").strip().lower()
    if action not in _ACTIONS:
        return {"ok": False, "said": "Jarvis does not know that media command."}
    try:
        out = deps.control(action)
    except Exception as exc:
        out = {"ok": False, "reason": type(exc).__name__}
    if out.get("ok"):
        return {"ok": True, "said": _SAID[action]}
    return {"ok": False, "said": _REASON_WORDS.get(str(out.get("reason") or ""),
                                                    _UNKNOWN_REASON)}


def now_playing(*, deps: Optional[Deps] = None) -> dict:
    """"What's playing?" {"ok", "said", "read"}. `read` names READ_MARK
    only when a real title is said - outside text, never learned, never
    saved."""
    deps = deps or DEPS
    try:
        out = deps.now_playing()
    except Exception as exc:
        out = {"ok": False, "reason": type(exc).__name__}
    if not out.get("ok"):
        return {"ok": False, "said": _REASON_WORDS.get(str(out.get("reason") or ""),
                                                        _UNKNOWN_REASON), "read": []}
    title, artist = _clip(out.get("title") or ""), _clip(out.get("artist") or "")
    if not title and not artist:
        return {"ok": True, "said": "Nothing seems to be playing right now.", "read": []}
    state = "Playing" if out.get("playing") else "Paused"
    if title and artist:
        said = f"{state}: “{title}” by {artist}."
    elif title:
        said = f"{state}: “{title}”."
    else:
        said = f"{state}: something by {artist}."
    return {"ok": True, "said": said, "read": [READ_MARK]}


# --------------------------------------------------------------------------
#   The route both apps call - no gate, no card, ever (see the module
#   docstring's "NEVER a card" paragraph)
# --------------------------------------------------------------------------

def handle_get() -> tuple:
    out = now_playing()
    return 200, {"ok": out["ok"], "said": out["said"]}


def handle_post(body) -> tuple:
    if not isinstance(body, dict) or not isinstance(body.get("action"), str):
        return 400, {"ok": False, "error": 'need {"action": "play"|"pause"|"next"|"previous"}'}
    action = body["action"].strip().lower()
    if action not in _ACTIONS:
        return 400, {"ok": False,
                     "error": 'action must be one of "play", "pause", "next", "previous"'}
    out = control(action)
    return (200 if out["ok"] else 503), out


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_GET` and `do_POST` so /api/media and
    /api/media/control are answered here, after the server's own origin and
    token checks - and nothing else: no jarvis_gate, no card, ever."""
    global _ARMED
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(post0, "_jarvis_media", False):
        _ARMED = True
        return "  media      Music and video control (already on)"

    def _allowed(self) -> bool:
        try:
            if not origin_ok(self):
                self._send(403, {"error": "cross-origin request refused"})
                return False
            if not token_ok(self):
                self._send(401, {"error": "bad or missing X-Jarvis-Token"})
                return False
        except Exception:
            self._send(401, {"error": "bad or missing X-Jarvis-Token"})
            return False
        return True

    def do_GET(self):
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route != PATH:
            return get0(self)
        if not _allowed(self):
            return None
        try:
            code, out = handle_get()
        except Exception as exc:
            code, out = 503, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    def do_POST(self):
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route != CONTROL_ROUTE:
            return post0(self)
        if not _allowed(self):
            return None
        try:
            import json
            body = json.loads(read_body(self) or b"{}")
        except Exception as exc:
            return self._send(400, {"error": type(exc).__name__})
        try:
            code, out = handle_post(body)
        except Exception as exc:
            code, out = 503, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    do_GET._jarvis_media = True
    do_POST._jarvis_media = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    _ARMED = True
    return "  media      Music and video control: play, pause, next, previous, what's playing"


_ARMED = False
