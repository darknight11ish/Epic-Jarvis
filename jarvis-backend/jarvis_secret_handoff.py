"""jarvis_secret_handoff.py - the owner-secret hand-off, and the 15-minute read
taint that follows a secret into a page or a window.

WHAT THIS IS FOR, IN ONE PARAGRAPH
Jarvis currently refuses a password-masked control outright
(`jarvis_ui_control.py`, `code` `password_control`). That is the right default
but it means Jarvis cannot log in anywhere for the owner. The owner-secret
hand-off keeps the refusal's safety while allowing the one flow that is safe:
the OWNER types the secret into the host (Jarvis's own card), the host types it
into the control the owner approved, and the value never enters model context,
a tool result, a database, a log line, the clipboard, or any file. Then, for 15
minutes, Jarvis refuses to READ that exact page or window back - so a
prompt-injected turn cannot immediately harvest what was just typed.

WHAT THIS MODULE IS, AND IS NOT
This is the RULE ENGINE and nothing else: the taint table, the hand-off card's
state machine, and the exact abort conditions. It holds no UI, opens no socket,
writes no file, and imports nothing outside the standard library. The wiring -
reading Windows UI Automation / the browser DOM to prove a target really is a
password field, raising the card, and the two injected typing functions - lives
in `jarvis_ui_control.py` and `jarvis_browser_control.py` in a later slice, so
today NOTHING imports this module and a backend without it behaves exactly as
before.

WHERE THE IDEAS COME FROM (CLEAN ROOM)
The shape is adapted from `makecindy/cindy` (Apache-2.0) - `secretTaint.ts` and
the input-hand-off product rules - which this project evaluated on 2026-10-26.
No source line was copied: the module is written against this project's own
rules (one card, no auto-approval, outside text, no CAPTCHA solving) and the
owner's decision of 2026-10-26 (hand-off first, the taint rule inside it).

THE TWO OBJECTS
  SecretPageTaintRegistry   in-memory only; at most SECRET_TAINT_MAX_KEYS
                            targets; SECRET_TAINT_TTL_S (15 min) each; keyed by
                            page address (scheme, host, path - the query string
                            and fragment are stripped) or by desktop window
                            (pid, hwnd, window class). It stores addresses and
                            numbers, never a secret value.
  SecretHandoffCoordinator  a bounded card lifecycle: create (only for a
                            password-masked target), then execute (verify the
                            live target has not changed, mark the taint BEFORE
                            the first character is typed, type through an
                            injected function, return a secret-free receipt).

WHAT IS NEVER DONE, AND EACH IS TESTED
  * the secret is never stored, logged, printed, audited or returned; there is
    no file, no database, no clipboard path in this module at all;
  * a card cannot be raised for anything but a password-masked control;
  * the fill aborts with ZERO characters typed if the target address/window,
    the control, or the password-field property changed since the card was
    raised, if the card is older than 180 s, if it is not answered on this PC,
    or if the value is empty or oversized;
  * the taint is marked before typing, so a typing failure still taints.

HONEST LIMITS, SAID PLAINLY
  * Python cannot guarantee that a secret is wiped from process memory. Strings
    are immutable; "overwriting" a local variable in a `finally:` block does
    nothing. What this module actually provides is: the value exists only for
    the duration of one synchronous call, is never copied into any structure it
    owns, and is never written anywhere. It is not a secure enclave.
  * The taint table is in memory only, so a backend restart clears it. That is
    intended: it is a session protection against a page being read back, not a
    durable record.
  * The taint keys are page addresses and window handles - not secrets - so a
    status surface may show them. Reviewer values never appear anywhere.
"""
from __future__ import annotations

import collections
import posixpath
import secrets
import threading
import time
import urllib.parse
from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple

#: How long a page/window stays read-locked after a secret was typed into it
#: (cindy uses 15 minutes; the owner's ruling of 2026-10-26 keeps that number).
SECRET_TAINT_TTL_S = 900.0
#: Most page/window keys held at once; oldest is evicted first.
SECRET_TAINT_MAX_KEYS = 32
#: How long the owner has to type the secret into the card and submit it.
HANDOFF_CARD_TTL_S = 180.0
#: Most cards pending at once, so a bug or a hostile loop cannot grow memory.
MAX_PENDING_CARDS = 16
#: A secret longer than this is refused rather than truncated.
SECRET_MAX_CHARS = 4096
#: The agent's claimed "what this is for" text is untrusted; it is cleaned,
#: capped and shown to the owner as a note, never as fact.
MAX_PURPOSE_CHARS = 120

_WEB_SCHEMES = ("http", "https")
_KINDS = ("browser", "desktop_window")


class SecretHandoffError(Exception):
    """Base class: something about a hand-off was refused."""


class SecretHandoffVoidedError(SecretHandoffError):
    """The hand-off step was voided; nothing (or nothing more) was typed."""


class SecretPageReadRestrictedError(SecretHandoffError):
    """An agent read targeted a page/window where a secret was just entered."""


def is_web_target_key(key: str) -> bool:
    """Whether a taint key names a page (`url:...`) rather than a window."""
    return isinstance(key, str) and key.startswith("url:")


def normalize_secret_target_key(*, url: str = "", pid: int = 0, hwnd: int = 0,
                                window_class: str = "") -> str:
    """The one normalized key for a hand-off target.

    For a browser page: `url:<scheme>://<host[:port]><path>` with the query
    string, the `#fragment` and any `user:pass@` userinfo stripped. Two
    spellings of the same page get the same key: scheme and host lower-cased,
    a default port (:80 http / :443 https) dropped, `.`/`..` path segments
    resolved and a trailing slash dropped. That keeps a one-time token, and a
    secret typed next to a login form, out of the key a refusal or a status
    surface can show. Only http/https is accepted.

    For a desktop window: `hwnd:<pid>:<hwnd>:<window class>`, lower-cased; an
    empty class becomes `-` rather than being silently dropped, so two windows
    of the same process cannot collide by omission.

    Raises ValueError for anything that is not one of those two shapes. It
    never echoes a full URL back in the error message: only the problem.
    """
    if isinstance(url, str) and url.strip():
        parsed = urllib.parse.urlsplit(url.strip())
        scheme = (parsed.scheme or "").lower()
        if scheme not in _WEB_SCHEMES:
            raise ValueError("a hand-off target page must be an http or https address")
        host = (parsed.hostname or "").lower()
        if not host:
            raise ValueError("a hand-off target page needs a host")
        try:
            port = parsed.port
        except ValueError:
            raise ValueError("a hand-off target page has an invalid port")
        default_port = 443 if scheme == "https" else 80
        host_text = f"[{host}]" if ":" in host else host
        if port is not None and port != default_port:
            host_text = f"{host_text}:{port}"
        path = posixpath.normpath(parsed.path or "/")
        path = "/" + path.lstrip("/")
        if path != "/" and path.endswith("/"):
            path = path.rstrip("/")
        return f"url:{scheme}://{host_text}{path}"
    try:
        ipid = int(pid)
        ihwnd = int(hwnd)
    except (TypeError, ValueError):
        raise ValueError("a hand-off target window needs a numeric pid and hwnd")
    if ipid <= 0 or ihwnd <= 0:
        raise ValueError("a hand-off target window needs a positive pid and hwnd")
    klass = str(window_class or "").strip().lower() or "-"
    return f"hwnd:{ipid}:{ihwnd}:{klass}"


def web_target_is_https(url: str) -> bool:
    """Whether an owner-supplied page address is encrypted (for the card badge)."""
    try:
        return (urllib.parse.urlsplit(str(url or "").strip()).scheme or "").lower() == "https"
    except ValueError:
        return False


def clean_agent_purpose(purpose: object) -> str:
    """The agent's claimed purpose, made safe to show as an untrusted note.

    Control characters and line breaks become spaces, runs collapse, and the
    text is capped at MAX_PURPOSE_CHARS. The card must label it as unverified;
    this function only makes it safe to render.
    """
    text = str(purpose or "")
    out = []
    for ch in text:
        out.append(" " if (ord(ch) < 0x20 or ord(ch) == 0x7F) else ch)
    cleaned = " ".join("".join(out).split())
    return cleaned[:MAX_PURPOSE_CHARS]


@dataclass(frozen=True)
class VerifiedTargetSnapshot:
    """What the HOST saw when it raised or checked a hand-off target.

    `target_key` comes from normalize_secret_target_key. `display_origin` is a
    host-built sentence (e.g. `https://github.com/login`, or
    `1Password.exe (PID 4812) - Unlock`) - never model text. `is_https` is the
    card's encrypted badge for a page; it is True for desktop windows because
    the badge does not apply there. `control_id` names the exact focused input
    the host found, so a focus change voids the step. `created_mono` is set by
    the coordinator, not by the caller.
    """

    target_key: str
    kind: str
    display_origin: str
    is_https: bool
    is_password_field: bool
    control_id: str
    agent_claimed_purpose: str = ""
    created_mono: float = 0.0

    def __post_init__(self) -> None:
        if self.kind not in _KINDS:
            raise ValueError(f"unknown hand-off target kind: {self.kind!r}")
        if not str(self.target_key or ""):
            raise ValueError("a hand-off snapshot needs a target key")
        if self.kind == "browser" and not is_web_target_key(self.target_key):
            raise ValueError("a browser hand-off needs a url: target key")
        if self.kind == "desktop_window" and is_web_target_key(self.target_key):
            raise ValueError("a desktop hand-off needs an hwnd: target key")
        if not str(self.control_id or ""):
            raise ValueError("a hand-off snapshot needs a control id")


class SecretPageTaintRegistry:
    """In-memory, bounded, monotonic-clock table of targets holding a secret.

    `clock` is injectable so tests never sleep; production uses
    `time.monotonic`, which cannot jump when the wall clock is adjusted.

    All state is a single OrderedDict of key -> expiry. Nothing here writes to
    disk, and no secret value is ever passed to this class - only target keys,
    which are page addresses or window handles.
    """

    def __init__(self, *, ttl_s: float = SECRET_TAINT_TTL_S,
                 max_keys: int = SECRET_TAINT_MAX_KEYS,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.ttl_s = float(ttl_s)
        self.max_keys = max(1, int(max_keys))
        self._clock = clock
        self._lock = threading.RLock()
        self._entries: "collections.OrderedDict[str, float]" = collections.OrderedDict()

    def _prune_locked(self, now: float) -> None:
        expired = [k for k, until in self._entries.items() if until <= now]
        for k in expired:
            self._entries.pop(k, None)
        while len(self._entries) > self.max_keys:
            self._entries.popitem(last=False)

    def mark_secret_entered(self, target_key: str) -> None:
        """Mark one target as read-locked for ttl_s from now (idempotent re-mark)."""
        if not str(target_key or ""):
            return
        with self._lock:
            now = self._clock()
            self._entries.pop(target_key, None)
            self._entries[target_key] = now + self.ttl_s
            self._prune_locked(now)

    def is_read_restricted(self, target_key: str) -> bool:
        if not str(target_key or ""):
            return False
        with self._lock:
            self._prune_locked(self._clock())
            return target_key in self._entries

    def require_read_allowed(self, target_key: str) -> None:
        """Raise the honest refusal when a read targets a just-secreted place."""
        if self.is_read_restricted(target_key):
            raise SecretPageReadRestrictedError(
                "Page/window read paused: a secret was recently entered into "
                f"'{target_key}'. Ask the owner to finish signing in or move to "
                "the next page, or wait for the taint to expire."
            )

    def clear_key(self, target_key: str) -> None:
        with self._lock:
            self._entries.pop(target_key, None)

    def clear_all(self) -> None:
        with self._lock:
            self._entries.clear()

    def active_keys(self) -> Tuple[str, ...]:
        """The currently read-locked target keys, oldest first (never secrets)."""
        with self._lock:
            self._prune_locked(self._clock())
            return tuple(self._entries.keys())

    def status(self) -> Dict[str, object]:
        """A small dict for a future status surface (no secret can appear here)."""
        keys = self.active_keys()
        return {
            "active": len(keys),
            "keys": list(keys),
            "ttl_seconds": int(self.ttl_s),
            "max_keys": int(self.max_keys),
        }


class SecretHandoffCoordinator:
    """The hand-off card's state machine: create, verify, taint, type, forget.

    `type_into_control_fn(control_id, secret_value)` is injected by the wiring
    layer (`jarvis_ui_control.py` for a desktop control, the browser controller
    for a page). This module never types anything itself, so the secret only
    crosses one function call and is not retained by anything it owns.
    """

    def __init__(self, taint_registry: Optional[SecretPageTaintRegistry] = None,
                 *, card_ttl_s: float = HANDOFF_CARD_TTL_S,
                 max_pending_cards: int = MAX_PENDING_CARDS,
                 clock: Callable[[], float] = time.monotonic,
                 handoff_id_factory: Optional[Callable[[], str]] = None) -> None:
        self.taint = taint_registry if taint_registry is not None \
            else SecretPageTaintRegistry(clock=clock)
        self.card_ttl_s = float(card_ttl_s)
        self.max_pending_cards = max(1, int(max_pending_cards))
        self._clock = clock
        self._id_factory = handoff_id_factory or (lambda: f"sh_{secrets.token_hex(12)}")
        self._lock = threading.RLock()
        self._pending: "collections.OrderedDict[str, VerifiedTargetSnapshot]" = \
            collections.OrderedDict()

    def _prune_pending_locked(self, now: float) -> None:
        expired = [hid for hid, snap in self._pending.items()
                   if (now - snap.created_mono) > self.card_ttl_s]
        for hid in expired:
            self._pending.pop(hid, None)

    def pending_count(self) -> int:
        with self._lock:
            self._prune_pending_locked(self._clock())
            return len(self._pending)

    def create_handoff_card(self, *, snapshot: VerifiedTargetSnapshot) -> Dict[str, object]:
        """Raise a card for ONE password-masked target. Returns card fields only.

        The returned dict is what the HUD renders: it never contains a secret
        (none exists yet) and it marks the agent's claimed purpose as untrusted
        by putting it in its own field. The host-verified fields are the ones
        the wiring layer measured immediately before this call.
        """
        if not snapshot.is_password_field:
            raise SecretHandoffVoidedError(
                "Refused the secret hand-off: the target control is not a "
                "password-masked input field."
            )
        now = self._clock()
        with self._lock:
            self._prune_pending_locked(now)
            if len(self._pending) >= self.max_pending_cards:
                raise SecretHandoffVoidedError(
                    "Too many secret hand-off cards are already waiting; the "
                    "oldest expired ones do not count. Finish or cancel one first."
                )
            handoff_id = self._id_factory()
            snap = VerifiedTargetSnapshot(
                target_key=snapshot.target_key, kind=snapshot.kind,
                display_origin=snapshot.display_origin, is_https=bool(snapshot.is_https),
                is_password_field=True, control_id=snapshot.control_id,
                agent_claimed_purpose=clean_agent_purpose(snapshot.agent_claimed_purpose),
                created_mono=now)
            self._pending[handoff_id] = snap
            return {
                "handoff_id": handoff_id,
                "verified_target": snap.display_origin,
                "target_kind": snap.kind,
                "is_https": snap.is_https,
                "is_password_field": True,
                "agent_claimed_purpose": snap.agent_claimed_purpose,
                "agent_purpose_is_untrusted": True,
                "from_this_pc_only": True,
                "expires_in_seconds": int(self.card_ttl_s),
            }

    def _void(self, message: str) -> "SecretHandoffVoidedError":
        return SecretHandoffVoidedError(message)

    def execute_owner_fill(
        self,
        handoff_id: str,
        secret_value: str,
        *,
        current_live_snapshot: VerifiedTargetSnapshot,
        type_into_control_fn: Callable[[str, str], None],
        from_this_pc: bool = False,
    ) -> Dict[str, object]:
        """Carry out an owner-approved hand-off, or void it with zero typed.

        The order below is the security property, not an implementation detail:
        every check runs BEFORE the first character is typed, and the 15-minute
        taint is marked BEFORE typing starts, so a failure halfway through
        typing still leaves the page/window read-locked.

        `from_this_pc` has no safe default: the wiring layer must assert that
        the request really came from this PC (loopback/host-only route and a
        verified caller). A caller that forgets to say so is refused with zero
        characters typed, not trusted.
        """
        if not from_this_pc:
            raise self._void("A secret hand-off card can only be answered on this PC.")
        with self._lock:
            snap = self._pending.get(handoff_id)
        if snap is None:
            raise self._void("That secret hand-off card is unknown, used or expired; "
                             "nothing was typed.")
        now = self._clock()
        if (now - snap.created_mono) > self.card_ttl_s:
            with self._lock:
                self._pending.pop(handoff_id, None)
            raise self._void("The secret hand-off card expired; nothing was typed.")
        if not isinstance(secret_value, str) or not secret_value.strip():
            raise self._void("The secret value is empty; nothing was typed.")
        if len(secret_value) > SECRET_MAX_CHARS:
            raise self._void(
                f"The secret is longer than {SECRET_MAX_CHARS} characters; nothing was typed.")

        live = current_live_snapshot
        if live.target_key != snap.target_key:
            raise self._void(
                f"The target changed while the card was open (card showed "
                f"'{snap.display_origin}', the host now sees "
                f"'{live.display_origin}'); nothing was typed.")
        if live.kind != snap.kind:
            raise self._void("The kind of target changed while the card was open; "
                             "nothing was typed.")
        if not live.is_password_field:
            raise self._void("The target control is no longer password-masked; "
                             "nothing was typed, so no secret was shown in clear.")
        if live.control_id != snap.control_id:
            raise self._void("The focused input control changed since the card was "
                             "raised; nothing was typed.")

        # The card is consumed exactly once, before anything is typed.
        with self._lock:
            consumed = self._pending.pop(handoff_id, None)
        if consumed is None:
            raise self._void("That secret hand-off card was already used.")

        # 1. Taint FIRST. A failure while typing must not leave the page readable.
        self.taint.mark_secret_entered(snap.target_key)
        # 2. Type through the injected function. A failure is reported with a
        #    fixed sentence: the injected exception is replaced rather than
        #    re-raised, so a third-party error string cannot echo the value it
        #    failed on into a log, a card or a tool result.
        try:
            type_into_control_fn(snap.control_id, secret_value)
        except Exception:
            raise SecretHandoffError(
                "Typing into the target failed; the page/window stays read-locked "
                "for the taint window. Check it before reading it back.") from None
        # 3. Return only metadata. `secret_value` goes out of scope here and is
        #    never stored anywhere in this object (see the module's honest limits).
        return {
            "ok": True,
            "handoff_id": handoff_id,
            "filled": True,
            "verified_target": snap.display_origin,
            "target_kind": snap.kind,
            "page_read_tainted": True,
            "taint_ttl_seconds": int(self.taint.ttl_s),
        }

    def abort_handoff(self, handoff_id: str) -> bool:
        """Owner pressed Cancel (or the wiring saw the target change): drop it."""
        with self._lock:
            return self._pending.pop(handoff_id, None) is not None


# --- the process-wide instance the wiring layer will use ---------------------

_TAINT = SecretPageTaintRegistry()
_HANDOFF = SecretHandoffCoordinator(_TAINT)


def taint_registry() -> SecretPageTaintRegistry:
    """The one taint table a wiring layer must consult before reading a page."""
    return _TAINT


def handoffs() -> SecretHandoffCoordinator:
    """The one card coordinator a wiring layer must use."""
    return _HANDOFF


def mark_secret_entered(target_key: str) -> None:
    _TAINT.mark_secret_entered(target_key)


def is_read_restricted(target_key: str) -> bool:
    return _TAINT.is_read_restricted(target_key)


def require_read_allowed(target_key: str) -> None:
    _TAINT.require_read_allowed(target_key)


def create_handoff_card(*, snapshot: VerifiedTargetSnapshot) -> Dict[str, object]:
    return _HANDOFF.create_handoff_card(snapshot=snapshot)


def execute_owner_fill(handoff_id: str, secret_value: str, *,
                       current_live_snapshot: VerifiedTargetSnapshot,
                       type_into_control_fn: Callable[[str, str], None],
                       from_this_pc: bool = True) -> Dict[str, object]:
    return _HANDOFF.execute_owner_fill(
        handoff_id, secret_value,
        current_live_snapshot=current_live_snapshot,
        type_into_control_fn=type_into_control_fn,
        from_this_pc=from_this_pc)


def reset_for_tests() -> None:
    """Reset the process-wide table and cards. Tests only; never called in production."""
    _TAINT.clear_all()
    while _HANDOFF._pending:            # pragma: no cover - defensive loop
        try:
            _HANDOFF._pending.popitem(last=False)
        except KeyError:
            break


__all__ = [
    "SECRET_TAINT_TTL_S", "SECRET_TAINT_MAX_KEYS", "HANDOFF_CARD_TTL_S",
    "MAX_PENDING_CARDS", "SECRET_MAX_CHARS", "MAX_PURPOSE_CHARS",
    "SecretHandoffError", "SecretHandoffVoidedError", "SecretPageReadRestrictedError",
    "normalize_secret_target_key", "clean_agent_purpose", "web_target_is_https",
    "is_web_target_key", "VerifiedTargetSnapshot", "SecretPageTaintRegistry",
    "SecretHandoffCoordinator", "taint_registry", "handoffs", "mark_secret_entered",
    "is_read_restricted", "require_read_allowed", "create_handoff_card",
    "execute_owner_fill", "reset_for_tests",
]
