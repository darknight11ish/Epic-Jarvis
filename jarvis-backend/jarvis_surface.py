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

THE PHONE'S OWN FACTS (2026-11-15). The owner asked for answers that are
*phone specific*, not just aware that a phone is asking: "make sure jarvis can
tell when im messaging from the phone and be more phone specific in the
answers". So the Android app also sends, on the same requests:

    X-Jarvis-Device: model=CPH2419;android=15;sdk=35;screen=1080x2400;app=0.2.4295

It is read once, by the same `remember` call, and `sentence()` appends one
short line naming the phone and asking for an answer sized to it. Absent - an
older app, the desktop, a script, a test - and `sentence()` is byte-for-byte
what it was before this existed.

LIVE OR AGED (2026-11-16). The facts stored for a request say when they
arrived (`device_age()`), and the newest report a phone has sent this process
is kept with its own time (`last_age()`). A fact that arrived with THIS
request is live; a stored one is returned with its age, and never presented as
a live check. `jarvis_quick.py` answers the model question from that rule -
see its `phone_own_facts` answer.

WHAT MAY ARRIVE. Only the five keys in `_DEVICE_KEYS`, each value stripped to
letters, digits, spaces and `. _ + -`, each capped, and the whole line capped at
`MAX_DEVICE_CHARS`. That is deliberate: this text reaches a system prompt, so a
fixed vocabulary is the only thing that may arrive - a newline, a brace or a
sentence shaped like an instruction is dropped, not escaped.

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

import re
import threading
import time
from typing import Any, Optional

#: The header the clients send. Lower-case on the wire is fine; HTTP headers
#: are case-insensitive and both clients send this exact name.
HEADER = "X-Jarvis-Surface"

PHONE = "phone"
DESKTOP = "desktop"
UNKNOWN = "unknown"

_KNOWN = (PHONE, DESKTOP)

#: The companion header the Android app sends with its own facts.
DEVICE_HEADER = "X-Jarvis-Device"

#: Longest device line read at all. The app caps itself far below this; this cap
#: is here so a broken or hostile caller cannot spend the model's window.
MAX_DEVICE_CHARS = 240

#: The only keys that mean anything, in the order they are shown. A key that is
#: not in this tuple is dropped rather than passed on: the line reaches a system
#: prompt, so a fixed vocabulary is the only thing that may arrive.
_DEVICE_KEYS = ("model", "android", "sdk", "screen", "app")

#: One value: letters, digits, spaces and `. _ + -`. Everything else - a
#: newline, a brace, a comma, a colon - is removed, which is what stops a
#: prompt-shaped sentence from being smuggled in.
_VALUE_OK = re.compile(r"[^A-Za-z0-9 ._+\-]")

#: Per-key value caps. A phone's model name is short; a value longer than this
#: is not one.
_DEVICE_VALUE_MAX = {"model": 28, "android": 8, "sdk": 3, "screen": 12, "app": 18}

#: The request's own surface, per thread. `ThreadingHTTPServer` answers one
#: request per thread; `origin_ok` writes it at the start of every request, so
#: a later read on the same thread is that request's surface. A thread that
#: never saw a header reads `unknown`.
#:
#: `device` is the phone's own facts for the same request (`X-Jarvis-Device`),
#: or an empty dict - which is every desktop request and every older client.
#: `device_at` is when they were stored (epoch seconds), so an answer can say
#: how old they are instead of presenting them as live.
_LOCAL = threading.local()

#: The newest facts any phone has sent THIS PROCESS, and when they arrived.
#: `remember` writes it on every request that carries the header, so a request
#: that did not come from the phone still has something honest to say - and
#: always WITH ITS AGE. Without it a desktop question would have no phone facts
#: at all, and naming a phone from the pairing record instead is the guess this
#: exists to prevent. In memory only: never written to disk, never logged, and
#: the line itself carries no identifier (see `DeviceFacts.kt`).
_LAST: dict = {"facts": {}, "at": 0.0}
_LAST_LOCK = threading.Lock()


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
    set_device(_device_header(headers))
    return surface


def set_current(surface) -> None:
    """Set this thread's surface (the tests' door, and `remember`'s half)."""
    _LOCAL.value = from_value(surface)


def current() -> str:
    """This request's surface: `phone`, `desktop`, or `unknown`."""
    return getattr(_LOCAL, "value", UNKNOWN) or UNKNOWN


def known() -> bool:
    return current() in _KNOWN


def _device_header(headers) -> str:
    """The raw `X-Jarvis-Device` value, or "" - never raises."""
    if headers is None:
        return ""
    try:
        getter = getattr(headers, "get", None)
        if getter is None:
            return ""
        return getter(DEVICE_HEADER)
    except Exception:
        return ""


def clean_facts(mapping) -> dict:
    """The five allowed keys, each cleaned and capped, or {} - never raises."""
    if not isinstance(mapping, dict):
        return {}
    out = {}
    for key in _DEVICE_KEYS:
        raw = mapping.get(key)
        if not isinstance(raw, str):
            continue
        clean = _VALUE_OK.sub("", raw).strip()
        if clean:
            out[key] = clean[:_DEVICE_VALUE_MAX[key]]
    return out


def from_device_value(value) -> dict:
    """`{"model": "CPH2419", "android": "15"}` from a `k=v;k=v` line, or {}.

    Every failure is the empty dict: not a string, empty, over
    `MAX_DEVICE_CHARS`, or carrying no known key. Nothing here raises, because
    it is called from the gate that every request passes through."""
    if not isinstance(value, str):
        return {}
    text = value.strip()
    if not text or len(text) > MAX_DEVICE_CHARS:
        return {}
    raw = {}
    for part in text.split(";"):
        key, sep, value_part = part.partition("=")
        if not sep:
            continue
        raw[key.strip().lower()] = value_part
    return clean_facts(raw)


def set_device(facts, at: Optional[float] = None) -> None:
    """Set this thread's phone facts (the tests' door, and `remember`'s half).

    Takes the header's own string or a mapping; anything else clears them.
    `at` is when they arrived (epoch seconds) and defaults to now: the real
    gate always stores them at the start of the request that carried them, so
    a timestamp in the past is the aged case a test needs. Facts that arrive
    are also kept as this process's newest report, which is what a request with
    no phone header reads."""
    clean = (from_device_value(facts) if isinstance(facts, str)
             else clean_facts(facts))
    when = float(time.time() if at is None else at)
    _LOCAL.device = clean
    _LOCAL.device_at = when
    if clean:
        set_last(clean, at=when)


def device() -> dict:
    """This request's phone facts: {} for the desktop, an older app or a test."""
    facts = getattr(_LOCAL, "device", None)
    return dict(facts) if isinstance(facts, dict) else {}


def device_at() -> float:
    """When this request's phone facts were stored (epoch seconds), or 0.0."""
    value = getattr(_LOCAL, "device_at", 0.0)
    return float(value) if isinstance(value, (int, float)) and value > 0 else 0.0


def device_age() -> Optional[float]:
    """Seconds since this request's phone facts arrived, or None without facts.

    This is the LIVE half: the facts are stored by `remember` at the start of
    the request that carried them, so a normal answer sees a few milliseconds
    and a test can pass `set_device(..., at=<past>)` to make them old."""
    if not device():
        return None
    at = device_at()
    return max(0.0, time.time() - at) if at else 0.0


def set_last(facts, at: Optional[float] = None) -> None:
    """Record the newest facts a phone has sent this process, with when.

    The door `remember` uses (through `set_device`) and the tests use to stand
    in for an earlier request. Empty facts are ignored, not a clear: a later
    desktop request must not erase the last report the phone sent."""
    clean = (from_device_value(facts) if isinstance(facts, str)
             else clean_facts(facts))
    if not clean:
        return
    with _LAST_LOCK:
        _LAST["facts"] = dict(clean)
        _LAST["at"] = float(time.time() if at is None else at)


def last() -> tuple:
    """The newest facts a phone has sent this process, and when: ({}, 0.0)."""
    with _LAST_LOCK:
        return dict(_LAST["facts"]), float(_LAST["at"])


def last_age() -> Optional[float]:
    """Seconds since the newest report, or None when no phone has sent one."""
    facts, at = last()
    if not facts or at <= 0:
        return None
    return max(0.0, time.time() - at)


def device_line() -> str:
    """One short line naming the phone, for the phone only; "" otherwise."""
    if current() != PHONE:
        return ""
    facts = device()
    if not facts:
        return ""
    bits = []
    if "model" in facts:
        bits.append(facts["model"])
    if "android" in facts:
        bits.append("Android " + facts["android"])
    elif "sdk" in facts:
        bits.append("Android SDK " + facts["sdk"])
    if "screen" in facts:
        bits.append("screen " + facts["screen"])
    if "app" in facts:
        bits.append("app " + facts["app"])
    if not bits:
        return ""
    return ("Phone: " + ", ".join(bits) + "."
            " Answer for a phone screen: short sentences, no tables."
            " If something can only be done on the PC, say so plainly.")


def sentence() -> str:
    """The one system-prompt sentence, or "" when the surface is unknown.

    On the phone it carries the phone's own facts as a second line when the app
    sent them. Without them - the desktop, an older app, a test - it is exactly
    the sentence it has always been."""
    surface = current()
    if surface == DESKTOP:
        return "The owner is talking to you from the desktop program."
    if surface != PHONE:
        return ""
    base = "The owner is talking to you from the Android app."
    extra = device_line()
    return base + ("\n" + extra if extra else "")


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
    """Forget this thread's surface and phone facts, and the newest report."""
    _LOCAL.value = UNKNOWN
    _LOCAL.device = {}
    _LOCAL.device_at = 0.0
    with _LAST_LOCK:
        _LAST["facts"] = {}
        _LAST["at"] = 0.0


def _fallback_unknown(value: Optional[Any]) -> str:
    """Kept tiny and private so old callers that passed an Optional still type-check."""
    return from_value(value)
