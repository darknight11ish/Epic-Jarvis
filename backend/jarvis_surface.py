"""jarvis_surface.py - which program the owner is talking to Jarvis from.

THE OWNER'S REQUIREMENT (2026-10-31): *Jarvis must know whether the owner is
talking from the Android app or the desktop program, and tailor its answers and
features accordingly - and it must work by default, with no setup.*

THE ONE FACT. Both clients send a plain header on every request:

    X-Jarvis-Surface: phone        (the Android app)
    X-Jarvis-Surface: desktop      (the desktop program)

It is additive, on top of the existing `X-Jarvis-Client: hud` that the origin
check requires. It is NOT authentication and NOT a secret: a request is allowed
or refused by the same origin + token checks as before, and this header only
chooses words. `X-Jarvis-Client` is deliberately unchanged, because the origin
check and the cloud-escalation rules read it.

HOW IT IS READ. The shipped origin gate (`jarvis_owner_check.origin_ok`) is
called by the Hud's do_POST for every chat request before anything answers, so
it remembers the surface for that request, once, on the request's own thread.
Nothing else has to be patched, and a request with no header - an older client,
a script, a test - stays `unknown` and behaves exactly as it did before.

WHAT USES IT.
  * `jarvis_quick.py`: the deterministic answers ("open settings", "open the
    second brain", feature/limits answers through `jarvis_feature_guide.py`).
  * `jarvis_agent.py`: one system sentence for the model, so general
    conversation can tailor itself too.
  * `jarvis_feature_guide.explain_words`: the feature list's own `surface` and
    `where` fields are read WITH the surface the owner is actually using.

FAIL-SAFE BY DESIGN. Every reading function here returns `unknown` rather than
raising: a module that cannot load, a headers object that is not a mapping, a
value that is neither "phone" nor "desktop" - all are `unknown`, which is the
old behaviour. Nothing here is ever logged, and the value is never treated as a
credential.
"""
from __future__ import annotations

import threading
from typing import Any, Optional

#: The header the clients send. Lower-case on the wire is fine; HTTP headers
#: are case-insensitive and both clients send this exact name.
HEADER = "X-Jarvis-Surface"

PHONE = "phone"
DESKTOP = "desktop"
UNKNOWN = "unknown"

_KNOWN = (PHONE, DESKTOP)

#: The request's own surface, per thread. `ThreadingHTTPServer` answers one
#: request per thread; `origin_ok` writes it at the start of every request, so
#: a later read on the same thread is that request's surface. A thread that
#: never saw a header reads `unknown`.
_LOCAL = threading.local()


def from_value(value) -> str:
    """"phone"/"desktop" from a header value; anything else is `unknown`."""
    if not isinstance(value, str):
        return UNKNOWN
    text = value.strip().lower()
    return text if text in _KNOWN else UNKNOWN


def from_headers(headers) -> str:
    """The surface named by a headers mapping (or `unknown`). Never raises."""
    if headers is None:
        return UNKNOWN
    try:
        getter = getattr(headers, "get", None)
        if getter is None:
            return UNKNOWN
        return from_value(getter(HEADER))
    except Exception:
        return UNKNOWN


def remember(headers) -> str:
    """Read once for THIS request and keep it for the rest of the request.

    Called by `jarvis_owner_check.origin_ok`, the shipped gate every chat
    request already passes through. Returns what was stored."""
    surface = from_headers(headers)
    set_current(surface)
    return surface


def set_current(surface) -> None:
    """Set this thread's surface (the tests' door, and `remember`'s half)."""
    _LOCAL.value = from_value(surface)


def current() -> str:
    """This request's surface: `phone`, `desktop`, or `unknown`."""
    return getattr(_LOCAL, "value", UNKNOWN) or UNKNOWN


def known() -> bool:
    return current() in _KNOWN


def sentence() -> str:
    """The one system-prompt sentence, or "" when the surface is unknown."""
    surface = current()
    if surface == PHONE:
        return "The owner is talking to you from the Android app."
    if surface == DESKTOP:
        return "The owner is talking to you from the desktop program."
    return ""


def asking_words() -> str:
    """"You are asking from the phone." / "... from the PC.", or ""."""
    surface = current()
    if surface == PHONE:
        return "You are asking from the phone."
    if surface == DESKTOP:
        return "You are asking from the PC."
    return ""


def route_words() -> str:
    """"on the phone" / "on the PC", or "" when unknown."""
    surface = current()
    if surface == PHONE:
        return "on the phone"
    if surface == DESKTOP:
        return "on the PC"
    return ""


def app_words() -> str:
    """"the phone app" / "the desktop program", or "" when unknown."""
    surface = current()
    if surface == PHONE:
        return "the phone app"
    if surface == DESKTOP:
        return "the desktop program"
    return ""


def reset() -> None:
    """Forget this thread's surface (the tests' own cleanup)."""
    try:
        del _LOCAL.value
    except AttributeError:
        pass


def _fallback_unknown(value: Optional[Any]) -> str:
    """Kept tiny and private so old callers that passed an Optional still type-check."""
    return from_value(value)
