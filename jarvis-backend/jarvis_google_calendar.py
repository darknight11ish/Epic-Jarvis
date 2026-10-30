"""jarvis_google_calendar.py - a real, two-way Google Calendar connection.

WHAT THE OWNER GETS, AND THE TWO WAYS IN

There are two ways to connect a Google calendar, and only one is ever active
(the owner chose "Both at once" on 2026-10-28: build both, and let him pick):

  1. Private link (read-only)  - the secret iCal address Google gives every
     calendar, pasted into the box that already exists in Settings, Accounts.
     jarvis_calendar.py already reads it; this module does not re-read it, it
     only remembers that this is the chosen way and points the reads at it. No
     browser, no token, no account, nothing new leaves the PC.

  2. Google sign-in (read/write) - this module. The owner creates a Google
     Cloud OAuth client ONCE (docs/GOOGLE-CALENDAR-SETUP.md), saves its client
     ID and secret with `py -3 jarvis_google_calendar.py client <id>`, and runs
     `connect`: his own browser opens, he signs in at Google, and Google
     redirects back to a listener on THIS PC that is bound to 127.0.0.1 only.

WHERE THE CHOICE IS MADE TODAY, said plainly: `py -3
jarvis_google_calendar.py mode off|ical|google`, in the backend folder, plus
`status`, `where`, `connect` and `disconnect` (see `_main` below). The desktop
Settings window has no door of its own to the backend - every Settings card in
this program is a Rust command, and `src-tauri/src/lib.rs` is where the parallel
account-connect work is - so the Settings row and the chat tool are NOT built
here. The routes below are the whole surface a Settings card or the account
tool needs when one lands, and `answer()` is the deterministic chat sentence,
wired into `jarvis_quick.py` by the 2026-10-28 integration branch (see "WIRING"
below for the position and why it is after the fast path, not before it).

WHY THE FLOW IS SHAPED THIS WAY (the rules that are not negotiable)

  * NO PUBLIC TUNNEL (CLAUDE.md rule 2). The redirect address is
    `http://127.0.0.1:<random port>/callback`. It is a `http.server.HTTPServer`
    bound with the literal host `127.0.0.1`, so Windows will not even accept a
    connection from another machine - there is no ngrok, no Cloudflare Tunnel,
    no Tailscale Funnel, and nothing to configure. `BIND_HOST` is a constant,
    not a setting, and a test refuses the file if it ever becomes "0.0.0.0" or
    "" (an empty host means every interface). This is the Google-documented
    "installed app / loopback IP address" flow, and it is the ONLY redirect
    shape Google still allows for a desktop app.
  * PKCE (RFC 7636, S256) AND A RANDOM `state`. The verifier never leaves this
    process and is never written anywhere; the challenge goes to Google. The
    callback looks at NOTHING until its `state` matches the one this flow
    started with (`hmac.compare_digest`) - not the code, and not Google's own
    `error=` - so a callback that did not come from the browser tab this flow
    opened is refused and NOTHING is exchanged. A wrong, missing or non-ASCII
    state is a refusal, never a warning and never an exception: it does not
    cancel the flow either, so nobody who can reach the loopback port can kill
    a sign-in by sending a bad `state` or a bare `error=`.
  * THE REFRESH TOKEN LIVES IN WINDOWS CREDENTIAL MANAGER (DPAPI, encrypted to
    this Windows account), through the SAME store helper the rest of the
    backend uses - `jarvis_token_store.WindowsStore`, not a second key store.
    Names:
        "Jarvis Backend/Google Calendar client secret"
        "Jarvis Backend/Google Calendar refresh token"
    The CLIENT ID is not a secret (it is in every auth URL the browser sees),
    so it lives in the settings file below, and the client secret never does.
    Unlike the four other named secrets, these two are read from Credential
    Manager ONLY - never from an environment variable. `resolve_secret()` puts
    the environment first by design, and an OAuth token in a plain-text
    environment variable is exactly what rule 3 forbids, so this module
    deliberately does not call it.
  * ACCESS TOKENS LIVE IN MEMORY ONLY. One dict, overwritten on refresh, never
    returned by a route, never in a card, never in an error, never in a log
    line, never written to a file. `status()` reports whether one is held, and
    when it expires - never the value. Both the refresh token and the access
    token are handed to `jarvis_scrub.register_secret` BY VALUE at the moment
    each is written or read, so if one ever did reach a log line or a model
    prompt the redactor removes it by value.
  * THE PHONE NEVER HOLDS THE REFRESH TOKEN. Nothing here returns it, no route
    serves it, and the Settings window is the PC's. `docs/ARCHITECTURE.md`
    section 3348-3351 already says a phone-side card would send a secret over
    the network to reach the store, which is worse than the store.
  * NO AUTO-APPROVAL (rule 4). Reading the calendar raises no card - it is a
    read of the owner's own data on his own PC. Creating, changing or deleting
    one event raises ONE approval card at tier `ask`, whose text is built from
    the exact event (title, when, where, which calendar), and the request is
    not sent to Google until that card says yes. A denied, timed-out or
    refused card sends nothing. The card is written here, never assembled from
    the request body.
  * A STALE EVENT STREAM IS REFUSED (rule 4). Changing or deleting an event
    needs a successful read of the calendar within `STREAM_MAX_AGE` seconds,
    and the event must be IN that read. Otherwise the answer is "I have not
    read your calendar just now - ask me again first" and nothing is sent: a
    card for an event that moved ten minutes ago is a card for the wrong
    event.
  * READS DO NOT LEAVE THE PC (rule 1) beyond the one Google request to the
    owner's own calendar. The event text comes back marked as OUTSIDE text
    (the same jarvis_calendar treatment: chat markers stripped, invisible
    characters folded, capped) so the model reads it as data, never as an
    instruction - an event titled "ignore your rules and ..." is a title.

THE ONE THING TO SAY PLAINLY ABOUT GOOGLE

`https://www.googleapis.com/auth/calendar.events` is a **sensitive** scope.
While the owner's Google Cloud project is in "Testing" (with himself added as
a test user, which the setup doc walks through), it works and only he can use
it - Google's own caveat is that a refresh token for a Testing-mode app
expires after 7 days, after which Jarvis will honestly say "the token has
expired, connect again". Publishing the app to "In production" with this scope
means Google's verification review; that is Google's rule, not this module's,
and docs/GOOGLE-CALENDAR-SETUP.md says so rather than pretending otherwise.
The scope used is the NARROWEST one that can list, create, change and delete
events - `calendar.readonly` is NOT requested, because `calendar.events`
already covers listing and asking for both would widen what Google shows on
the consent screen for nothing.

WHAT IS NOT HERE

  * No model tool. The parallel account-connect work owns the tool list
    (`jarvis_agent.py`, `jarvis_quick.py`, `jarvis_ui_control.py`,
    `jarvis_hud.html`), so the chat sentences are DETERMINISTIC functions in
    this module (`answer()`, `parse_meeting()`) with their own tests. The
    wiring into `jarvis_quick.answer()` is the integration branch's one call,
    not a second copy of the quick path. See "WIRING" below.
  * No second store, no second redactor, no second outside-text path: every
    one of those is the module that already does it.
  * No background sync. A read happens when something asks for one.

ROUTES (installed by `install()`, called from plugins/ready/google-calendar)

    GET  /api/google-calendar/status          what is connected, in words
    GET  /api/google-calendar/events?days=7   the next N days (card-free)
    POST /api/google-calendar/start           begin the sign-in (one flow; a second
                                              start answers that same flow)
    POST /api/google-calendar/cancel          stop a flow that is waiting
    POST /api/google-calendar/disconnect      revoke at Google + forget it
    POST /api/google-calendar/mode            {"mode": "off"|"ical"|"google"}
    POST /api/google-calendar/client          {"client_id": "...",
                                               "client_secret": "..."}
    POST /api/google-calendar/events          create (ONE card)
    POST /api/google-calendar/events/update   change (ONE card)
    POST /api/google-calendar/events/delete   delete (ONE card)

WIRING: DONE IN THE INTEGRATION BRANCH, AND THE POSITION MOVED FOR A REASON

The 2026-10-28 integration branch calls `answer()` from `jarvis_quick.answer()` -
but AFTER `intent = match(text, now)`, not before it. The original note said
"before `match`, because no quick intent owns these sentences"; that stopped
being true the day the connect-account work merged, because its grammar owns
"connect my calendar" and `answer()` also carries a connect sentence. Asking
this module first would shadow the connect card, which is the wrong card for
that sentence. One owner per sentence, and the table is pinned by
`backend/test_calendar_answer.py` (`t_one_owner_per_sentence`):

  * "connect my calendar" (and "set up github", "is my calendar connected?") ->
    the connect-account CARD, `jarvis_quick._connect`;
  * the setup shapes that card does not claim ("calendar setup", "sync my
    calendar with jarvis") -> `calendar_setup`;
  * a read ("what's on my calendar today") or an event ("add a meeting Tuesday
    3pm") -> this module's `answer()`, asked LAST, so it cannot compete.

Two facts shape the call:

  * `answer()` below returns `Optional[str]` - one sentence, or None.
  * `jarvis_quick.answer()` returns `Optional[Result]` (a dataclass), and its
    caller then runs `res.reply = in_manner(res.reply, ...)`. A bare string
    returned from that function breaks the turn: a `str` has no `.reply`. The
    sentence must be wrapped in a `Result`.

The call, as `jarvis_quick.answer()` now has it, inside `if intent is None:` -
after the fast path has declined, before returning None to the model - and
guarded because a private chat must not reach Google:

    if not private:
        try:
            import jarvis_google_calendar as _gcal
            _said = _gcal.answer(text)
        except Exception:
            _said = None
        if _said is not None:
            return Result(str(_said), "google_calendar", read=["calendar_read"])

From that position a connect sentence never reaches `answer()`, so its own
connect sentence is unreachable from chat ON PURPOSE. No model tool is added, so
`tools/check_invoke_grants.py` stays green.

WHAT THAT WIRING STILL DOES NOT DO: create an event. `answer()` only DESCRIBES
a proposed event ("I can add ... it needs one approval card"); nothing is sent
to Google by it. Creating one needs a second, explicit step -
`create_event(parse_meeting(text), ...)` after an explicit yes - and that step
is not wired, so a chat sentence can describe an event but cannot create one.
`create_event()` returns a `(status, dict)` tuple for the route; it does not
return an event dictionary, and nothing here hands one back to chat.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from dataclasses import dataclass, field
from datetime import date, datetime, time as _time, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit

# --------------------------------------------------------------------------
#   What Google is told, and the two names the settings file may hold
# --------------------------------------------------------------------------

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
REVOKE_ENDPOINT = "https://oauth2.googleapis.com/revoke"
API_BASE = "https://www.googleapis.com/calendar/v3"

#: The narrowest scope that can list, create, change and delete events.
#: `calendar.readonly` is deliberately NOT here: `calendar.events` already
#: covers listing, and a second scope would widen Google's consent screen for
#: nothing. A test pins this tuple to exactly one entry.
SCOPES = ("https://www.googleapis.com/auth/calendar.events",)

#: Credential Manager names. The client secret and the refresh token are the
#: two secrets; the client ID is public and lives in the settings file.
TARGET_CLIENT_SECRET = "Jarvis Backend/Google Calendar client secret"
TARGET_REFRESH = "Jarvis Backend/Google Calendar refresh token"

#: The three modes. "off" stops using either way and KEEPS the stored token
#: (the owner may switch back); "disconnect" is the separate act that revokes.
MODES = ("off", "ical", "google")

#: The settings file: the chosen mode and the client ID. NEVER a secret -
#: `_REFUSED_FIELDS` below is the list a write may not carry.
SETTINGS_NAME = "google-calendar.json"
_REFUSED_FIELDS = ("client_secret", "refresh_token", "access_token",
                   "code", "code_verifier", "state")

#: The listener's host and path. A CONSTANT, not a setting: loopback only.
BIND_HOST = "127.0.0.1"
CALLBACK_PATH = "/callback"

#: How long a started sign-in waits for the browser to come back.
FLOW_SECONDS = 600.0

#: How old the last successful read may be before a change or a delete is
#: refused as stale (rule 4).
STREAM_MAX_AGE = 300.0

_MAX_FIELD_CHARS = 300
_MAX_EVENTS = 50
_MAX_BYTES = 1024 * 1024
_HTTP_TIMEOUT = 20.0
_DAYS_CAP = 90

#: The plain words for each outcome of a card. Same shape as jarvis_vault's.
LAST_WORDS = {
    "approved": "Done - and the change is in your Google Calendar.",
    "denied": "Nothing was changed - you said no.",
    "timed_out": "Nothing was changed - the card timed out.",
    "refused": "Nothing was changed.",
    "failed": "Nothing was changed - Google refused or the PC could not send it.",
    "stale": "Nothing was changed - I have not read your calendar just now. Ask me again first.",
}


class FlowError(Exception):
    """A sign-in could not be started or finished. Carries a sentence, never a
    token, never the verifier, never a code."""


class NotConnected(Exception):
    """There is no usable Google connection. The sentence says what is
    missing in plain words."""


# --------------------------------------------------------------------------
#   The settings file - the chosen mode and the client ID, never a secret
# --------------------------------------------------------------------------

#: Tests point this at a throwaway folder, so a suite never reads or writes
#: the owner's own ~/.openjarvis. Nothing in the product sets it.
_CONFIG_DIR_OVERRIDE: Optional[Path] = None


def _config_dir() -> Path:
    """The folder the rest of the backend uses, found the same way
    (jarvis_accounts._config_dir mirrors jarvis_search._config_dir; this
    mirrors both, so google-calendar.json sits beside accounts.json)."""
    if _CONFIG_DIR_OVERRIDE is not None:
        return Path(_CONFIG_DIR_OVERRIDE)
    fw = _fw()
    if fw is not None:
        try:
            return Path(fw.CONFIG_DIR)
        except Exception:
            pass
    env = os.environ.get("OPENJARVIS_CONFIG_DIR")
    if env:
        return Path(os.path.expanduser(env))
    return Path(os.path.expanduser("~")) / ".openjarvis"


def settings_path() -> Path:
    return _config_dir() / SETTINGS_NAME


def _fw():
    """jarvis_framework, or None - the backend this ships into may not have
    it, and nothing here may fail to import because of that."""
    try:
        import jarvis_framework  # type: ignore
        return jarvis_framework
    except Exception:
        return None


def _read_settings() -> tuple:
    """(document, why it could not be read). Never raises; a damaged file
    reads as empty rather than guessing a mode."""
    path = settings_path()
    try:
        if not path.is_file():
            return {}, ""
        raw = path.read_text(encoding="utf-8")
        doc = json.loads(raw)
    except Exception as exc:
        return {}, f"the settings file could not be read ({type(exc).__name__})"
    if not isinstance(doc, dict):
        return {}, "the settings file is not a JSON object"
    return doc, ""


def _write_settings(doc: dict) -> None:
    """Write the two allowed fields, atomically, and refuse a secret.

    The refusal is the point: this file is plain text on disk, so a secret in
    it would break rule 3 no matter how carefully it was typed."""
    for key in _REFUSED_FIELDS:
        if key in doc:
            raise ValueError(f"{key} is never written to {SETTINGS_NAME} - "
                             f"secrets live in Windows Credential Manager")
    clean = {k: doc[k] for k in ("mode", "client_id") if k in doc}
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(clean, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def mode() -> str:
    doc, _why = _read_settings()
    chosen = str(doc.get("mode") or "off")
    return chosen if chosen in MODES else "off"


def client_id() -> str:
    """The public half of the OAuth client. Not a secret, so it may be shown
    back to the owner - it is in every auth URL the browser sees."""
    doc, _why = _read_settings()
    value = doc.get("client_id")
    return value.strip() if isinstance(value, str) else ""


# --------------------------------------------------------------------------
#   The store - the SAME helper the rest of the backend uses
# --------------------------------------------------------------------------

#: Tests replace this with a factory of stand-in stores (target -> object with
#: read()/write()/delete()), exactly as jarvis_vault's own tests do.
_STORE_FACTORY: Optional[Callable[[str], object]] = None


def _store(target: str):
    if _STORE_FACTORY is not None:
        return _STORE_FACTORY(target)
    try:
        import jarvis_token_store
        return jarvis_token_store.default_store(target)
    except Exception as exc:
        return _StoreProblem(f"Credential Manager could not be opened ({type(exc).__name__})")


class _StoreProblem(Exception):
    """There is no store here. A sentence, never a value."""


def _register(value: str) -> None:
    """Hand a token to the redactor, by value. Never raises."""
    if not value:
        return
    try:
        import jarvis_scrub
        jarvis_scrub.register_secret(value)
    except Exception:
        pass


def _read_secret(target: str) -> str:
    """The value in Credential Manager under `target`, or "".

    No environment fallback on purpose - see the module docstring."""
    st = _store(target)
    if isinstance(st, Exception):
        return ""
    try:
        value = st.read() or ""
    except Exception:
        return ""
    value = str(value).strip()
    if value:
        _register(value)
    return value


def _write_secret(target: str, value: str) -> bool:
    """Write it and read it back. True only when the read-back matches.

    The value is handed to the redactor HERE as well as on every later read -
    otherwise the refresh token written at exchange time would not be
    registered with `jarvis_scrub` until something happened to read it back,
    and the docstring's promise ("registered by value") would be false for the
    whole window in which it is most likely to be logged.

    No plaintext copy is left anywhere: the store is the only place it goes,
    and `jarvis_token_store.WindowsStore.write` zeroes its own byte copy."""
    st = _store(target)
    if isinstance(st, Exception):
        return False
    try:
        st.write(value)
        back = str(st.read() or "").strip()
    except Exception:
        return False
    if bool(back) and hmac.compare_digest(back, value):
        _register(value)
        return True
    return False


def _delete_secret(target: str) -> bool:
    st = _store(target)
    if isinstance(st, Exception):
        return False
    try:
        return bool(st.delete())
    except Exception:
        return False


def client_secret_present() -> bool:
    return bool(_read_secret(TARGET_CLIENT_SECRET))


def refresh_token_present() -> bool:
    return bool(_read_secret(TARGET_REFRESH))


# --------------------------------------------------------------------------
#   Access tokens - memory only
# --------------------------------------------------------------------------

_ACCESS: dict = {"token": "", "expires_at": 0.0}
#: The calendar's own name (Google's "primary" calendar summary), for the
#: status line only. Never an address Jarvis sends anything to.
_ACCOUNT: dict = {"name": ""}
_LOCK = threading.RLock()

#: Everything a write needs to know about the last read: when it happened
#: (monotonic) and WHAT it saw, by event id - the event's own summary and times,
#: not just the id. A change to an id that is not in the snapshot is refused
#: rather than sent blind, and a card is built from the snapshot so it can never
#: show one event while deleting another.
_STATE: dict = {"last_read": 0.0, "events": {}}


def _reset_for_tests() -> None:
    global _STORE_FACTORY, _TRANSPORT, _OPENER
    cancel()
    with _LOCK:
        _ACCESS["token"], _ACCESS["expires_at"] = "", 0.0
        _ACCOUNT["name"] = ""
        _STATE["last_read"], _STATE["events"] = 0.0, {}
    with _PENDING_LOCK:
        _PENDING["flow"] = None
    _STORE_FACTORY = None
    _TRANSPORT = None
    _OPENER = None


# --------------------------------------------------------------------------
#   HTTP - one injected seam, https only, no redirects followed
# --------------------------------------------------------------------------

#: (method, url, form-or-None, headers) -> (status, parsed JSON or {})
#: Tests replace it; nothing else does. Every real call goes through
#: `_default_transport`, which cannot follow a redirect and talks https only.
_TRANSPORT: Optional[Callable[[str, str, Optional[dict], Optional[dict]], tuple]] = None


def _default_transport(method: str, url: str, payload: Optional[dict],
                        headers: Optional[dict]) -> tuple:
    """One https request with http.client - no library to install, and no
    redirect handler to leave the host. A 3xx is returned as-is, which every
    caller treats as a failure, so a redirect can never carry a token to
    another address.

    `payload` is the body: urlencoded (the OAuth endpoints want that) unless
    the caller's own Content-Type says JSON (the Calendar API wants that)."""
    import http.client

    parts = urlsplit(url)
    if parts.scheme != "https":
        raise FlowError("Google is only ever reached over https")
    path = parts.path + (("?" + parts.query) if parts.query else "")
    body = None
    hdrs = dict(headers or {})
    if payload is not None:
        if "json" in str(hdrs.get("Content-Type", "")).lower():
            body = json.dumps(payload).encode("utf-8")
        else:
            body = urlencode(payload).encode("utf-8")
            hdrs.setdefault("Content-Type", "application/x-www-form-urlencoded")
    hdrs.setdefault("Accept", "application/json")
    conn = http.client.HTTPSConnection(parts.hostname or "", parts.port or 443,
                                       timeout=_HTTP_TIMEOUT)
    try:
        conn.request(method, path, body=body, headers=hdrs)
        resp = conn.getresponse()
        raw = resp.read(_MAX_BYTES)
        status = int(resp.status)
    finally:
        try:
            conn.close()
        except Exception:
            pass
    try:
        parsed = json.loads(raw.decode("utf-8")) if raw else {}
    except Exception:
        parsed = {}
    return status, parsed if isinstance(parsed, dict) else {}


def _call(method: str, url: str, *, form: Optional[dict] = None,
          headers: Optional[dict] = None,
          transport: Optional[Callable] = None) -> tuple:
    fn = transport or _TRANSPORT or _default_transport
    try:
        status, body = fn(method, url, form, headers)
    except FlowError:
        raise
    except Exception as exc:
        # The exception's NAME only: its message can carry the URL.
        raise FlowError(f"the request could not be sent ({type(exc).__name__})") from None
    return int(status), (body if isinstance(body, dict) else {})


# --------------------------------------------------------------------------
#   PKCE and state - the two things that make the callback safe
# --------------------------------------------------------------------------

def make_verifier() -> str:
    """A fresh PKCE code verifier (RFC 7636: 43-128 characters from the
    unreserved set). 64 bytes of entropy, base64url, unpadded = 86 chars."""
    return base64.urlsafe_b64encode(secrets.token_bytes(64)).decode("ascii").rstrip("=")


def challenge_for(verifier: str) -> str:
    """S256: base64url(sha256(ascii(verifier))), unpadded."""
    digest = hashlib.sha256(str(verifier).encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def make_state() -> str:
    return secrets.token_urlsafe(32)


def state_matches(expected: str, given: Any) -> bool:
    """Constant-time, and a missing or non-text state is never a match.

    A state Jarvis makes is always ASCII (`secrets.token_urlsafe`), so a
    non-ASCII `given` can never be the real one - and it must be REFUSED
    rather than raise: `hmac.compare_digest` raises `TypeError` on a non-ASCII
    `str`, and an exception here would escape `do_GET` and close the listener,
    killing a sign-in nobody authenticated. Every value is refused safely."""
    if not isinstance(given, str) or not given or not expected:
        return False
    expected = str(expected)
    if not expected or not expected.isascii() or not given.isascii():
        return False
    return hmac.compare_digest(expected, given)


# --------------------------------------------------------------------------
#   The flow: start -> loopback callback -> exchange -> tokens
# --------------------------------------------------------------------------

@dataclass
class Flow:
    """One sign-in in flight. Nothing here is logged or returned whole: the
    verifier never leaves this object and the state is only returned inside
    the URL Google is given."""
    state: str
    verifier: str
    redirect_uri: str
    port: int
    deadline: float
    #: The URL the browser was sent to. It holds the state and the challenge,
    #: never the verifier, and it is what a second `start` answers with so two
    #: clicks cannot open two listeners.
    url: str = ""
    #: Whether the browser was handed the URL (so a second `start` can answer
    #: truthfully instead of claiming it opened another one).
    opened: bool = False
    server: Any = None
    thread: Any = None
    done: Any = field(default_factory=threading.Event)
    result: dict = field(default_factory=dict)
    lock: Any = field(default_factory=threading.Lock)

    def finish(self, **result) -> None:
        with self.lock:
            if self.done.is_set():
                return
            self.result.update(result)
            self.done.set()

    def outcome(self) -> dict:
        """What happened, in words a person can act on - never a token."""
        with self.lock:
            out = dict(self.result)
        out.setdefault("outcome", "waiting")
        if out["outcome"] == "waiting" and time.time() > self.deadline:
            out["outcome"] = "timed_out"
        return out


#: The one flow allowed at a time. A second `start` while one is WAITING
#: answers that same flow and opens no second listener; a flow that already
#: finished (or timed out) is reaped and replaced. `_START_LOCK` serialises the
#: whole start, so a burst of `POST /start` cannot leave an orphan listener that
#: no `_PENDING` entry points at (each one would otherwise live up to
#: FLOW_SECONDS). Lock order: `_START_LOCK` then `_PENDING_LOCK`, never the
#: other way round, and nothing here calls `cancel()` while holding either.
_PENDING: dict = {"flow": None}
_PENDING_LOCK = threading.Lock()
_START_LOCK = threading.Lock()

#: Tests replace this. The real one hands the URL to the default browser -
#: which is the owner's own browser, on the owner's own PC.
_OPENER: Optional[Callable[[str], Any]] = None


def _open(url: str) -> bool:
    """Hand the sign-in URL to the default browser. Never raises, and never
    logs the URL (it holds the state and the challenge, not a secret - but a
    URL in a log is still a URL in a log)."""
    fn = _OPENER
    if fn is not None:
        try:
            fn(url)
            return True
        except Exception:
            return False
    try:
        import webbrowser
        return bool(webbrowser.open(url))
    except Exception:
        return False


def auth_url(flow: Flow, client: str) -> str:
    """The URL the browser is sent to. `access_type=offline` is what asks for
    a refresh token, and `prompt=consent` makes Google hand one back every
    time - without it a second sign-in can come back with an access token
    only, and Jarvis would work until it expired and then stop."""
    query = {
        "client_id": client,
        "redirect_uri": flow.redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "state": flow.state,
        "code_challenge": challenge_for(flow.verifier),
        "code_challenge_method": "S256",
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    }
    return AUTH_ENDPOINT + "?" + urlencode(query)


def _page(handler: BaseHTTPRequestHandler, status: int, title: str, body: str) -> None:
    """One small page in the browser tab. Fixed text only - nothing from the
    query string is echoed back (a reflected `state` would be a way to put
    attacker-chosen words in the owner's browser)."""
    html = (
        "<!doctype html><meta charset='utf-8'>"
        "<title>{t}</title>"
        "<style>body{{font-family:Segoe UI,system-ui,sans-serif;max-width:34rem;"
        "margin:12vh auto;padding:0 1.5rem;line-height:1.5;color:#1b1b1f}}"
        "h1{{font-size:1.3rem}}</style>"
        "<h1>{t}</h1><p>{b}</p>"
    ).format(t=title, b=body).encode("utf-8")
    try:
        handler.send_response(status)
        handler.send_header("Content-Type", "text/html; charset=utf-8")
        handler.send_header("Content-Length", str(len(html)))
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Referrer-Policy", "no-referrer")
        handler.end_headers()
        handler.wfile.write(html)
    except Exception:
        pass


class _CallbackHandler(BaseHTTPRequestHandler):
    """Answers exactly one path: /callback. Everything else is a 404, and no
    request can make this handler tell anyone anything about the flow."""

    server_version = "Jarvis"
    sys_version = ""

    def log_message(self, fmt, *args):     # noqa: A003 - stdlib's name
        """Nothing goes to stderr: a query string holds the code and the
        state, and http.server's default line would write both to a log."""
        return

    def do_GET(self):                       # noqa: N802 - stdlib's name
        flow: Flow = getattr(self.server, "jarvis_flow", None)
        parts = urlsplit(str(self.path or ""))
        if flow is None or parts.path.rstrip("/") != CALLBACK_PATH:
            _page(self, 404, "Not here",
                  "This address only answers the sign-in Google sends back.")
            return
        query = dict(parse_qsl(parts.query, keep_blank_values=True))

        # THE STATE CHECK, BEFORE ANYTHING IS ACTED ON. A callback that did not
        # come from the tab this flow opened is refused and nothing is
        # exchanged - and it must also not FINISH the flow: anything that can
        # reach this loopback port is unauthenticated, so a bad or missing
        # state that cancelled the sign-in here would be a way to kill a
        # sign-in nobody asked that attacker to touch. The flow stays waiting;
        # a real bad state (an old tab) simply expires.
        if not state_matches(flow.state, query.get("state")):
            _page(self, 400, "That sign-in did not start here",
                  "Jarvis refused it because the code did not match the sign-in "
                  "it started. Nothing was saved, and the sign-in Jarvis started "
                  "is still waiting - finish it in the tab that opened it, or "
                  "close this tab and start again from Jarvis.")
            return

        # A refusal from Google itself: the owner pressed Cancel, or the
        # client is misconfigured. It only reaches this branch with the RIGHT
        # state, so only the browser tab this flow opened can end it. The CODE
        # is recorded for the status line; the page says fixed words and never
        # echoes the query, so nothing chosen by whoever reached this address
        # can appear in the owner's browser.
        if query.get("error"):
            err = str(query.get("error"))[:60]
            flow.finish(outcome="denied" if err == "access_denied" else "error",
                        error=err)
            _page(self, 400, "Sign-in was not finished",
                  "Google did not finish the sign-in, so nothing was saved and "
                  "nothing was sent to your calendar. You can close this tab and "
                  "start again from Jarvis.")
            self._stop()
            return

        code = query.get("code")
        if not isinstance(code, str) or not code:
            flow.finish(outcome="bad_request")
            _page(self, 400, "No code came back",
                  "Google did not send an authorization code, so nothing was "
                  "saved. Start the connection again from Jarvis.")
            self._stop()
            return

        try:
            result = exchange_code(code, flow.verifier, flow.redirect_uri)
        except FlowError as exc:
            flow.finish(outcome="exchange_failed", error=str(exc))
            _page(self, 500, "Google would not finish the sign-in",
                  "{} Nothing was saved. You can close this tab.".format(exc))
            self._stop()
            return
        except Exception as exc:                    # never the message
            flow.finish(outcome="exchange_failed", error=type(exc).__name__)
            _page(self, 500, "Google would not finish the sign-in",
                  "Something went wrong on this PC ({}). Nothing was saved."
                  .format(type(exc).__name__))
            self._stop()
            return

        flow.finish(outcome="connected",
                    account=result.get("account", ""),
                    expires_at=result.get("expires_at", 0.0))
        _page(self, 200, "Jarvis is connected to your Google Calendar",
              "You can close this tab and go back to Jarvis.")
        self._stop()

    def _stop(self) -> None:
        flow: Flow = getattr(self.server, "jarvis_flow", None)
        if flow is not None:
            flow.done.set()


def exchange_code(code: str, verifier: str, redirect_uri: str, *,
                  transport: Optional[Callable] = None) -> dict:
    """Swap the one-time code for tokens, and put the refresh token in
    Credential Manager.

    Returns {"account", "expires_at"} - never a token. The access token is
    kept in `_ACCESS` (memory only); the refresh token goes straight into the
    store and is not returned to the caller at all, so no route, log line or
    card can carry it by accident."""
    client = client_id()
    secret = _read_secret(TARGET_CLIENT_SECRET)
    if not client:
        raise FlowError("the Google client ID has not been saved on this PC")
    if not secret:
        raise FlowError("the Google client secret has not been saved on this PC")
    status, body = _call("POST", TOKEN_ENDPOINT, form={
        "code": code,
        "code_verifier": verifier,
        "client_id": client,
        "client_secret": secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }, transport=transport)
    if status != 200:
        # Google's own error CODE only (`invalid_grant`, `redirect_uri_mismatch`
        # ...), never the body: the body of a token response is where the
        # tokens are.
        raise FlowError("Google refused the code ({})".format(
            str(body.get("error") or "Google answered with error number {}".format(status))[:60]))
    refresh = body.get("refresh_token")
    if not isinstance(refresh, str) or not refresh:
        raise FlowError("Google did not send a refresh token, so Jarvis would stop "
                        "working when the first access token expired - connect again "
                        "and leave the consent screen's boxes ticked")
    if not _write_secret(TARGET_REFRESH, refresh):
        raise FlowError("the refresh token could not be saved to Windows Credential "
                        "Manager, so nothing was kept")
    _keep_access(body)
    account = ""
    try:
        account = _whoami(body.get("access_token") or "", transport=transport)
    except Exception:
        account = ""
    with _LOCK:
        _ACCOUNT["name"] = account
    # Signing in IS choosing this way: the two options on the Settings row are
    # exclusive, and the owner just proved which one he wants. Best effort -
    # a settings file that cannot be written must not undo a real connection.
    try:
        doc, _why = _read_settings()
        doc["mode"] = "google"
        _write_settings(doc)
    except Exception:
        pass
    return {"account": account, "expires_at": _ACCESS.get("expires_at", 0.0)}


def _keep_access(body: dict) -> None:
    """Remember the access token in memory only, never on disk."""
    token = body.get("access_token")
    if not isinstance(token, str) or not token:
        return
    try:
        expires_in = float(body.get("expires_in") or 3500)
    except Exception:
        expires_in = 3500.0
    with _LOCK:
        _ACCESS["token"] = token
        # A minute of margin, so a request never races the expiry.
        _ACCESS["expires_at"] = time.time() + max(60.0, expires_in - 60.0)
    _register(token)


def _whoami(access: str, *, transport: Optional[Callable] = None) -> str:
    """The signed-in address, for the status line - ONE read of the owner's
    own profile, and "" when it cannot be read. Never a token."""
    if not access:
        return ""
    status, body = _call("GET", API_BASE + "/calendars/primary", headers={
        "Authorization": "Bearer " + access}, transport=transport)
    if status != 200:
        return ""
    return _outside_field(body.get("summary") or "")


def access_token(*, transport: Optional[Callable] = None,
                  force_refresh: bool = False) -> str:
    """A usable access token, refreshed from Credential Manager when the one
    in memory has expired. Raises `NotConnected` in plain words."""
    with _LOCK:
        token = _ACCESS.get("token") or ""
        expires_at = float(_ACCESS.get("expires_at") or 0.0)
        if token and not force_refresh and time.time() < expires_at:
            return token

    refresh = _read_secret(TARGET_REFRESH)
    if not refresh:
        raise NotConnected("Google Calendar is not connected yet")
    client = client_id()
    secret = _read_secret(TARGET_CLIENT_SECRET)
    if not (client and secret):
        raise NotConnected("the Google client ID and secret are not saved on this PC")
    status, body = _call("POST", TOKEN_ENDPOINT, form={
        "client_id": client,
        "client_secret": secret,
        "refresh_token": refresh,
        "grant_type": "refresh_token",
    }, transport=transport)
    if status != 200:
        err = str(body.get("error") or "Google answered with error number {}".format(status))[:60]
        if err == "invalid_grant":
            raise NotConnected("the saved Google permission has expired - run "
                               "`py -3 jarvis_google_calendar.py connect` in the "
                               "backend folder again (Google deletes a Testing-mode "
                               "token after about 7 days)")
        raise NotConnected("Google would not renew the connection ({})".format(err))
    if not isinstance(body.get("access_token"), str) or not body.get("access_token"):
        raise NotConnected("Google answered without a token")
    _keep_access(body)
    with _LOCK:
        return _ACCESS["token"]


def _answer_for(flow: Flow, clock: Callable[[], float]) -> dict:
    """The start() answer for a flow - never the verifier, never a token."""
    return {"auth_url": flow.url, "port": flow.port,
            "redirect_uri": flow.redirect_uri,
            "browser_opened": bool(flow.opened),
            "expires_in": max(0, int(flow.deadline - clock()))}


def start(*, opener: Optional[Callable[[str], Any]] = None,
          transport: Optional[Callable] = None,
          clock: Callable[[], float] = time.time) -> dict:
    """Begin a sign-in: bind the loopback listener, build the URL, and hand it
    to the browser. Returns {"auth_url", "port", "redirect_uri", "expires_in"}
    - never the verifier, never a token.

    The listener is bound to `BIND_HOST` (127.0.0.1) on an ephemeral port, so
    there is nothing to forward and nothing another machine can reach.

    ONE listener at a time, and that is a lock rather than a convention: a
    second `start` while the first is still WAITING answers the SAME flow (so a
    double click on a Settings button cannot kill a sign-in or open a second
    listener); a flow that already finished or timed out is finished here and
    its listener closed before the new one binds. A burst of `POST /start`
    therefore leaves exactly one live listener, not one per request.
    """
    client = client_id()
    if not client:
        raise FlowError("the Google client ID has not been saved on this PC yet")
    if not _read_secret(TARGET_CLIENT_SECRET):
        raise FlowError("the Google client secret has not been saved on this PC yet")

    with _START_LOCK:
        with _PENDING_LOCK:
            current = _PENDING.get("flow")
            still_waiting = (current is not None and not current.done.is_set()
                             and clock() <= current.deadline)
            if still_waiting:
                return _answer_for(current, clock)
            if current is not None:           # finished or timed out: reap it
                current.finish(outcome="cancelled")
                try:
                    current.server.server_close()
                except Exception:
                    pass

            server = HTTPServer((BIND_HOST, 0), _CallbackHandler)
            server.daemon_threads = True
            server.timeout = 0.25
            host, port = server.server_address[0], int(server.server_address[1])
            if host != BIND_HOST:             # cannot happen; refuse anyway
                server.server_close()
                raise FlowError("the sign-in listener refused to bind to loopback only")

            flow = Flow(state=make_state(), verifier=make_verifier(),
                        redirect_uri="http://{}:{}{}".format(BIND_HOST, port,
                                                             CALLBACK_PATH),
                        port=port, deadline=clock() + FLOW_SECONDS, server=server)
            flow.url = auth_url(flow, client)
            server.jarvis_flow = flow
            _PENDING["flow"] = flow

        # Opening the browser and starting the thread happen while `_START_LOCK`
        # is still held, so a concurrent `start` sees a flow that is already
        # running and answers it rather than adding a second listener.
        flow.thread = threading.Thread(target=_serve, args=(server, flow),
                                       name="jarvis-google-calendar-callback",
                                       daemon=True)
        flow.thread.start()
        flow.opened = (_open(flow.url) if opener is None
                       else bool(_try(lambda: opener(flow.url))))
        return _answer_for(flow, clock)


def _try(fn) -> bool:
    try:
        return bool(fn())
    except Exception:
        return False


def _serve(server: HTTPServer, flow: Flow) -> None:
    """Accept requests until the flow finishes or its deadline passes, then
    close the listener. One thread, no busy loop."""
    try:
        while not flow.done.is_set():
            try:
                server.handle_request()
            except Exception:
                break
            if time.time() > flow.deadline:
                flow.finish(outcome="timed_out")
                break
    finally:
        try:
            server.server_close()
        except Exception:
            pass
        # The flow is deliberately LEFT in `_PENDING`: its outcome is what the
        # Settings window polls and what `wait()` returns after the browser
        # tab has already been answered. A new `start()` replaces it.


def pending() -> Optional[Flow]:
    with _PENDING_LOCK:
        return _PENDING.get("flow")


def cancel() -> bool:
    """Stop a sign-in that is waiting. True if there was one. Nothing is
    saved, and the state it used can never be answered again."""
    flow = pending()
    if flow is None:
        return False
    flow.finish(outcome="cancelled")
    try:
        flow.server.server_close()
    except Exception:
        pass
    return True


def wait(timeout: float = 5.0) -> dict:
    """Wait for the flow in flight, for the Settings window's poll and for the
    tests. Returns the outcome in words; never a token."""
    flow = pending()
    if flow is None:
        return {"outcome": "none"}
    flow.done.wait(max(0.0, float(timeout)))
    return flow.outcome()


# --------------------------------------------------------------------------
#   Reads - the chosen way, card-free
# --------------------------------------------------------------------------

def _outside_plain(text: Any) -> str:
    """Event text with the project's own tricks removed - the SAME treatment
    jarvis_calendar gives a feed event (chat markers stripped, invisible
    characters folded), reused lazily rather than copied."""
    text = str(text or "")
    try:
        import jarvis_calendar
        fn = getattr(jarvis_calendar, "_outside_plain", None)
        if callable(fn):
            return str(fn(text))
    except Exception:
        pass
    try:
        import jarvis_agent
        text = jarvis_agent.strip_chat_markers(text)
    except Exception:
        pass
    return text


def _outside_field(value: Any) -> str:
    return _outside_plain(value)[:_MAX_FIELD_CHARS]


def _event_row(item: dict) -> dict:
    """One Google event as a bounded row Jarvis may read out. Every text field
    is outside text and capped; nothing is invented."""
    start = item.get("start") if isinstance(item.get("start"), dict) else {}
    end = item.get("end") if isinstance(item.get("end"), dict) else {}
    all_day = bool(start.get("date")) and not start.get("dateTime")
    return {
        "id": str(item.get("id") or "")[:200],
        "summary": _outside_field(item.get("summary") or "(no title)"),
        "start": _outside_field(start.get("dateTime") or start.get("date") or ""),
        "end": _outside_field(end.get("dateTime") or end.get("date") or ""),
        "all_day": all_day,
        "where": _outside_field(item.get("location") or ""),
        "calendar": "primary",
    }


def _snapshot(rows: list) -> dict:
    """What the last read saw, by event id: the event's OWN summary and times.

    The card for a change or a delete is built from this, never from the
    request, so it cannot display one event while deleting another - and an
    update card can show the values that were there before as well as the ones
    that will replace them."""
    seen: dict = {}
    for row in rows:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        seen[str(row["id"])] = {
            "summary": str(row.get("summary") or "(no title)"),
            "start": str(row.get("start") or ""),
            "end": str(row.get("end") or ""),
            "where": str(row.get("where") or ""),
            "all_day": bool(row.get("all_day")),
        }
    return seen


def _window(days_ahead: int, *, now: Optional[datetime] = None) -> tuple:
    days = max(1, min(_DAYS_CAP, int(days_ahead)))
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment, moment + timedelta(days=days)


def _list_google(days_ahead: int, *, now: Optional[datetime] = None,
                  transport: Optional[Callable] = None) -> dict:
    start_at, end_at = _window(days_ahead, now=now)
    token = access_token(transport=transport)
    query = urlencode({
        "timeMin": start_at.isoformat().replace("+00:00", "Z"),
        "timeMax": end_at.isoformat().replace("+00:00", "Z"),
        "singleEvents": "true",
        "orderBy": "startTime",
        "maxResults": str(_MAX_EVENTS),
    })
    status, body = _call("GET", API_BASE + "/calendars/primary/events?" + query,
                         headers={"Authorization": "Bearer " + token},
                         transport=transport)
    if status != 200:
        reason = str((body.get("error") or {}) if isinstance(body.get("error"), dict)
                     else {}).get("message") or "Google answered with error number {}".format(status)
        return {"ok": False, "connected": True, "events": [],
                "reason": "Google refused the calendar read ({})".format(
                    _outside_field(reason)[:120])}
    items = body.get("items")
    rows = [_event_row(i) for i in (items if isinstance(items, list) else [])
            if isinstance(i, dict)][:_MAX_EVENTS]
    with _LOCK:
        _STATE["last_read"] = time.monotonic()
        _STATE["events"] = _snapshot(rows)
    return {"ok": True, "connected": True, "events": rows,
            "days": max(1, min(_DAYS_CAP, int(days_ahead))),
            "window": {"from": start_at.isoformat(), "to": end_at.isoformat()}}


def _list_ical(days_ahead: int, *, now: Optional[datetime] = None) -> dict:
    """The private link, read by jarvis_calendar.py - not a second reader."""
    try:
        import jarvis_calendar
    except Exception:
        return {"ok": False, "connected": False, "events": [],
                "reason": "the calendar reader is not on this backend"}
    plan = jarvis_calendar.plan(days_ahead, now=now)
    got = jarvis_calendar.run(plan, approved=True)
    if not got.get("ok"):
        return {"ok": False, "connected": bool(plan.query), "events": [],
                "reason": str(got.get("reason") or "the private link could not be read")}
    rows = []
    for ev in got.get("events") or []:
        if not isinstance(ev, dict):
            continue
        rows.append({"id": str(ev.get("id") or "")[:200],
                     "summary": _outside_field(ev.get("summary") or "(no title)"),
                     "start": _outside_field(ev.get("start") or ""),
                     "end": _outside_field(ev.get("end") or ""),
                     "all_day": bool(ev.get("all_day")),
                     "where": _outside_field(ev.get("where") or ""),
                     "calendar": "private link (read-only)"})
    return {"ok": True, "connected": True, "events": rows[:_MAX_EVENTS],
            "read_only": True, "days": max(1, min(_DAYS_CAP, int(days_ahead)))}


#: The owner-facing answer when no way in is chosen, and it has to be TRUE ON
#: THE PHONE as well as the PC. The phone field test of 2026-10-29 (B2) found
#: an old sentence that sent the owner to "Settings, Accounts, pick the private
#: link or Google sign-in" on a phone that has no Accounts screen; the HUD field
#: test of the same day found that the newer text named a Google sign-in ROW
#: that does not exist. So this names only places that exist: the Accounts card
#: on the PC for the read-only private iCal link, and the one-time Google
#: sign-in commands in SETUP_DOC for the read/write way. "not connected yet" is
#: said ONCE - `answer()` hands this sentence on as it stands rather than
#: prefixing "Not connected yet - " to it.
SETUP_DOC = "docs/GOOGLE-CALENDAR-SETUP.md"

_NOT_CONNECTED_WORDS = (
    "Google Calendar is not connected yet. On the PC, open Settings, Accounts and "
    "paste in your calendar's private iCal link (read-only), or run the one-time "
    "Google sign-in commands in " + SETUP_DOC + ".")

#: A reason that already says this is a whole answer, not a clause to hang
#: another "Not connected yet - " in front of. The B2 defect: the phone read
#: "Not connected yet - Google Calendar is not connected yet - ...".
_SAYS_NOT_CONNECTED = re.compile(r"(?i)\bnot connected\b")


def list_events(days_ahead: int = 7, *, now: Optional[datetime] = None,
                transport: Optional[Callable] = None) -> dict:
    """The next N days, by whichever way is chosen. Card-free: a read of the
    owner's own calendar on his own PC.

    Always returns {"ok", "connected", "events", "reason"?} - "not connected
    yet" is an honest answer, never an empty calendar."""
    chosen = mode()
    if chosen == "off":
        return {"ok": False, "connected": False, "events": [],
                "reason": _NOT_CONNECTED_WORDS}
    if chosen == "ical":
        return _list_ical(days_ahead, now=now)
    try:
        return _list_google(days_ahead, now=now, transport=transport)
    except NotConnected as exc:
        return {"ok": False, "connected": False, "events": [], "reason": str(exc)}
    except FlowError as exc:
        return {"ok": False, "connected": False, "events": [], "reason": str(exc)}


# --------------------------------------------------------------------------
#   The card, and the gate that must say yes - one per write, never auto
# --------------------------------------------------------------------------

ACTION_WRITE = "google_calendar_write"

#: The gate stops waiting at `approval_timeout_seconds` (600 as shipped); the
#: route waits that plus this much, so a person who reads the card for six
#: minutes and then says yes is obeyed rather than told "nothing was changed".
_WAIT_AFTER_GATE = 30.0
_GATE_TIMEOUT_FALLBACK = 600.0


def _gate_timeout() -> float:
    try:
        import jarvis_gate
        seconds = float(getattr(jarvis_gate, "APPROVAL_TIMEOUT", 0) or 0)
        return seconds if seconds > 0 else _GATE_TIMEOUT_FALLBACK
    except Exception:
        return _GATE_TIMEOUT_FALLBACK


def _gate(action: str, detail: dict, prompt: str):
    """jarvis_gate.check(), failing closed: a route that cannot ask a person
    must not change a calendar."""
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _tier_of(action: str) -> str:
    try:
        fw = _fw()
        return str(fw.action_tier(action))
    except Exception:
        return "ask"


def _person_said_yes(v) -> bool:
    """A person's yes, and nothing weaker: tier must BE "ask" and the outcome
    "approved" - `allowed` alone is true on tier `notify` with nobody asked."""
    if getattr(v, "allowed", False) is not True:
        return False
    if getattr(v, "tier", None) != "ask":
        return False
    return getattr(v, "outcome", None) == "approved"


def _spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="jarvis-google-calendar-card", daemon=True).start()


CARD_TITLES = {
    "create": "Jarvis wants to add an event to your Google Calendar",
    "update": "Jarvis wants to change an event in your Google Calendar",
    "delete": "Jarvis wants to delete an event from your Google Calendar",
}

CARD_WHY = ("Nothing is sent to Google until you say yes. The card shows the exact "
            "event: the title, when, where and which calendar.")


def _words(kind: str, event: dict) -> str:
    """The card's own text: the values that will be sent, and - for a change -
    the values the last read actually saw, so the person can see both."""
    when = "{} to {}".format(event.get("start", "?"), event.get("end", "?"))
    lines = [CARD_TITLES[kind], "", CARD_WHY, "",
             "What:  " + str(event.get("summary") or "(no title)"),
             "When:  " + when,
             "Where: " + (str(event.get("where") or "-")),
             "Calendar: primary"]
    old = event.get("previous") or {}
    if kind == "update" and old:
        lines += ["", "It is like this now, and this is what the card changes:",
                  "What:  " + str(old.get("summary") or "(no title)"),
                  "When:  " + "{} to {}".format(old.get("start") or "?",
                                                old.get("end") or "?"),
                  "Where: " + str(old.get("where") or "-")]
    if event.get("description"):
        lines.append("Notes: " + str(event["description"])[:300])
    return "\n".join(lines)


def _card_says_yes(kind: str, event: dict, *, gate=None, tier_of=None,
                    spawn=None) -> tuple:
    """(True, "") only on a person's yes. (False, outcome) otherwise. Blocks
    until the card is answered or the gate gives up - said plainly rather
    than described as non-blocking."""
    detail = {
        "what": "{} a Google Calendar event".format(kind),
        "kind": kind,
        "summary": event.get("summary", ""),
        "start": event.get("start", ""),
        "end": event.get("end", ""),
        "where": event.get("where", ""),
        "previous": event.get("previous") or {},
        "event_id": event.get("id", ""),
        "leaves_this_pc": True,
        "text": CARD_TITLES[kind],
        "card": _words(kind, event),
    }
    gate = gate or _gate
    tier_of = tier_of or _tier_of
    spawn = spawn or _spawn
    box: dict = {}

    def ask() -> None:
        try:
            box["verdict"] = gate(ACTION_WRITE, detail, detail["card"])
        except Exception as exc:
            box["error"] = type(exc).__name__

    try:
        spawn(ask)
    except Exception:
        return False, "refused"
    deadline = time.time() + _gate_timeout() + _WAIT_AFTER_GATE
    while "verdict" not in box and "error" not in box and time.time() < deadline:
        time.sleep(0.02)
    if "error" in box or "verdict" not in box:
        return False, "refused"
    v = box["verdict"]
    if not _person_said_yes(v):
        outcome = getattr(v, "outcome", None)
        return False, outcome if outcome in ("denied", "timed_out") else "refused"
    if tier_of(ACTION_WRITE) != "ask":
        # The gate answered a yes at some other tier: the tier is no longer
        # the one this module was written for. Refuse.
        return False, "refused"
    return True, ""


# --------------------------------------------------------------------------
#   Writes - create / update / delete, one card each
# --------------------------------------------------------------------------

def _refuse(code: int, why: str, outcome: str = "refused") -> tuple:
    return code, {"ok": False, "outcome": outcome, "error": why,
                  "message": LAST_WORDS.get(outcome, LAST_WORDS["refused"])}


def _need_google() -> None:
    if mode() != "google":
        raise NotConnected("Google sign-in is not the chosen way on this PC - run "
                           "`py -3 jarvis_google_calendar.py mode google` in the "
                           "backend folder")
    if not refresh_token_present():
        raise NotConnected("Google Calendar is not connected yet - run "
                           "`py -3 jarvis_google_calendar.py connect` in the backend "
                           "folder")


def stale_reason(*, now: Optional[float] = None) -> str:
    """Why a change or a delete must not be sent, or "". Rule 4: a card for an
    event whose stream is stale is a card for the wrong event."""
    with _LOCK:
        last = float(_STATE.get("last_read") or 0.0)
    if not last:
        return "I have not read your calendar this run"
    current = time.monotonic() if now is None else float(now)
    if current - last > STREAM_MAX_AGE:
        return "I read your calendar {:.0f} minutes ago, which is too long to act on".format(
            (current - last) / 60.0)
    return ""


def _start_field(value: Any) -> Optional[dict]:
    """Google's start/end field for a date or a date-and-time string."""
    text = str(value or "").strip()
    if not text:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return {"date": text}
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return {"dateTime": moment.isoformat()}


def _event_body(fields: dict) -> Optional[dict]:
    """The JSON Google is sent, from the five values the card showed. Every
    field is capped here; an unknown field is dropped, never forwarded."""
    start = _start_field(fields.get("start"))
    end = _start_field(fields.get("end"))
    if start is None or end is None:
        return None
    body = {"summary": str(fields.get("summary") or "(no title)")[:300],
            "start": start, "end": end}
    if fields.get("where"):
        body["location"] = str(fields["where"])[:300]
    if fields.get("description"):
        body["description"] = str(fields["description"])[:2000]
    return body


def _send_json(method: str, url: str, body: dict, *,
               transport: Optional[Callable] = None) -> tuple:
    """A JSON body through the one transport seam (the form seam is for the
    OAuth endpoints, which want urlencoded)."""
    token = access_token(transport=transport)
    fn = transport or _TRANSPORT or _default_transport
    try:
        status, out = fn(method, url, body, {"Authorization": "Bearer " + token,
                                             "Content-Type": "application/json"})
    except FlowError:
        raise
    except Exception as exc:
        raise FlowError("the request could not be sent ({})".format(
            type(exc).__name__)) from None
    return int(status), (out if isinstance(out, dict) else {})


def create_event(fields: dict, *, gate=None, tier_of=None, spawn=None,
                 transport: Optional[Callable] = None) -> tuple:
    """POST /api/google-calendar/events - ONE event, after ONE card."""
    try:
        _need_google()
    except NotConnected as exc:
        return _refuse(409, str(exc))
    body = _event_body(fields)
    if body is None:
        return _refuse(400, "an event needs a start and an end (a date, or a date "
                            "and time)")
    shown = {"summary": body["summary"],
             "start": str(fields.get("start") or ""),
             "end": str(fields.get("end") or ""),
             "where": str(fields.get("where") or ""),
             "description": str(fields.get("description") or "")}
    yes, outcome = _card_says_yes("create", shown, gate=gate, tier_of=tier_of,
                                  spawn=spawn)
    if not yes:
        code = 403 if outcome in ("denied", "timed_out") else 503
        return _refuse(code, "nothing was sent to Google", outcome)
    try:
        status, out = _send_json("POST", API_BASE + "/calendars/primary/events",
                                 body, transport=transport)
    except NotConnected as exc:
        return _refuse(409, str(exc))
    except FlowError as exc:
        return _refuse(503, str(exc), "failed")
    if status not in (200, 201):
        return _refuse(502, "Google refused the new event (error number {})".format(status), "failed")
    with _LOCK:
        _STATE["last_read"], _STATE["events"] = 0.0, {}   # the list is now out of date
    return 200, {"ok": True, "outcome": "approved", "event": _event_row(out),
                 "message": LAST_WORDS["approved"]}


def update_event(fields: dict, *, gate=None, tier_of=None, spawn=None,
                 transport: Optional[Callable] = None) -> tuple:
    """POST /api/google-calendar/events/update - ONE card, and only for an
    event the last read really saw. The card shows the values that read saw
    ("It is like this now") as well as the ones that will replace them."""
    try:
        _need_google()
    except NotConnected as exc:
        return _refuse(409, str(exc))
    event_id = str(fields.get("event_id") or "").strip()
    if not event_id or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", event_id):
        return _refuse(400, "which event? an event id from the last read is needed")
    stale = stale_reason()
    with _LOCK:
        previous = dict((_STATE.get("events") or {}).get(event_id) or {})
    if stale:
        return _refuse(409, stale, "stale")
    if not previous:
        return _refuse(409, "that event is not in the calendar I last read, so I will "
                            "not change it blind", "stale")
    body = _event_body(fields)
    if body is None:
        return _refuse(400, "a change needs the start and the end as well as the title")
    shown = {"id": event_id, "summary": body["summary"],
             "start": str(fields.get("start") or ""),
             "end": str(fields.get("end") or ""),
             "where": str(fields.get("where") or ""),
             "description": str(fields.get("description") or ""),
             "previous": previous}
    yes, outcome = _card_says_yes("update", shown, gate=gate, tier_of=tier_of,
                                  spawn=spawn)
    if not yes:
        code = 403 if outcome in ("denied", "timed_out") else 503
        return _refuse(code, "nothing was sent to Google", outcome)
    try:
        status, out = _send_json("PATCH", API_BASE + "/calendars/primary/events/" + event_id,
                                 body, transport=transport)
    except NotConnected as exc:
        return _refuse(409, str(exc))
    except FlowError as exc:
        return _refuse(503, str(exc), "failed")
    if status != 200:
        return _refuse(502, "Google refused the change (error number {})".format(status), "failed")
    with _LOCK:
        _STATE["last_read"], _STATE["events"] = 0.0, {}
    return 200, {"ok": True, "outcome": "approved", "event": _event_row(out),
                 "message": LAST_WORDS["approved"]}


def delete_event(fields: dict, *, gate=None, tier_of=None, spawn=None,
                 transport: Optional[Callable] = None) -> tuple:
    """POST /api/google-calendar/events/delete - ONE card, and only for an
    event the last read really saw.

    Only the id comes from the request. The card's title and times are the ones
    the last read saw for that id, so the card cannot describe one event while
    the DELETE goes to another."""
    try:
        _need_google()
    except NotConnected as exc:
        return _refuse(409, str(exc))
    event_id = str(fields.get("event_id") or "").strip()
    if not event_id or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", event_id):
        return _refuse(400, "which event? an event id from the last read is needed")
    stale = stale_reason()
    with _LOCK:
        previous = dict((_STATE.get("events") or {}).get(event_id) or {})
    if stale:
        return _refuse(409, stale, "stale")
    if not previous:
        return _refuse(409, "that event is not in the calendar I last read, so I will "
                            "not delete it blind", "stale")
    shown = {"id": event_id,
             "summary": previous.get("summary") or "(the event)",
             "start": previous.get("start") or "",
             "end": previous.get("end") or "",
             "where": previous.get("where") or ""}
    yes, outcome = _card_says_yes("delete", shown, gate=gate, tier_of=tier_of,
                                  spawn=spawn)
    if not yes:
        code = 403 if outcome in ("denied", "timed_out") else 503
        return _refuse(code, "nothing was sent to Google", outcome)
    try:
        status, out = _send_json("DELETE", API_BASE + "/calendars/primary/events/" + event_id,
                                 {}, transport=transport)
    except NotConnected as exc:
        return _refuse(409, str(exc))
    except FlowError as exc:
        return _refuse(503, str(exc), "failed")
    if status not in (200, 204):
        return _refuse(502, "Google refused the delete (error number {})".format(status), "failed")
    with _LOCK:
        _STATE["last_read"], _STATE["events"] = 0.0, {}
    return 200, {"ok": True, "outcome": "approved", "deleted": event_id,
                 "message": "Deleted from your Google Calendar."}


# --------------------------------------------------------------------------
#   Disconnect and the chooser
# --------------------------------------------------------------------------

def disconnect(*, revoke: bool = True,
               transport: Optional[Callable] = None) -> dict:
    """Stop using Google, and by default ask Google to forget the permission.

    The refresh token is deleted from Credential Manager either way, so Jarvis
    stops using it immediately; `revoked` says truthfully whether Google
    confirmed the revoke, because a deletion here is not a deletion there."""
    refresh = _read_secret(TARGET_REFRESH)
    revoked, detail = False, ""
    if refresh and revoke:
        try:
            status, body = _call("POST", REVOKE_ENDPOINT, form={"token": refresh},
                                 transport=transport)
            revoked = status in (200, 400)   # 400 = it was already invalid
            if not revoked:
                detail = "Google answered with error number {}".format(status)
        except FlowError as exc:
            detail = str(exc)
    had = _delete_secret(TARGET_REFRESH)
    with _LOCK:
        _ACCESS["token"], _ACCESS["expires_at"] = "", 0.0
        _ACCOUNT["name"] = ""
        _STATE["last_read"], _STATE["events"] = 0.0, {}
    doc, _why = _read_settings()
    if doc.get("mode") == "google":
        doc["mode"] = "off"
        try:
            _write_settings(doc)
        except Exception:
            pass
    if not refresh:
        message = "There was nothing to disconnect."
    elif not revoke:
        message = ("Forgotten on this PC. Google still lists a permission for Jarvis - "
                   "remove it at myaccount.google.com/permissions if you want it gone "
                   "there too.")
    elif revoked:
        message = "Disconnected, and Google was asked to forget the permission."
    else:
        message = ("Disconnected on this PC. Google's record of the permission could "
                   "not be revoked here, so remove it at "
                   "myaccount.google.com/permissions too.")
    return {"ok": True, "revoked": revoked, "forgotten_locally": bool(had),
            "detail": detail, "message": message}


def set_mode(chosen: str) -> dict:
    """Pick one of the two ways, or off. Switching off KEEPS the stored token -
    disconnect() is the separate act that revokes."""
    chosen = str(chosen or "").strip().lower()
    if chosen not in MODES:
        raise ValueError("pick one of: " + ", ".join(MODES))
    if chosen == "google":
        if not client_id() or not _read_secret(TARGET_CLIENT_SECRET):
            raise ValueError("save the Google client ID and client secret first - "
                             "docs/GOOGLE-CALENDAR-SETUP.md walks through it")
        if not refresh_token_present():
            raise ValueError("sign in to Google first: run `py -3 "
                             "jarvis_google_calendar.py connect` in the backend folder")
    if chosen == "ical":
        link = _ical_link()
        if not link:
            raise ValueError("paste your calendar's private iCal address in the box "
                             "above first (Google Calendar, Settings, the calendar, "
                             "Integrate calendar)")
    doc, _why = _read_settings()
    doc["mode"] = chosen
    _write_settings(doc)
    with _LOCK:
        if chosen != "google":
            _STATE["last_read"], _STATE["events"] = 0.0, {}
    return {"ok": True, "mode": chosen}


def _ical_link() -> str:
    try:
        import jarvis_calendar
        return jarvis_calendar._feed_url()
    except Exception:
        return ""


def set_client(client_id_value: Optional[str] = None,
               client_secret_value: Optional[str] = None) -> dict:
    """Save the public client ID in settings and the client secret in
    Credential Manager. Never echoes either one back."""
    if client_id_value is not None:
        cid = str(client_id_value).strip()
        if cid and not re.fullmatch(r"[A-Za-z0-9._-]{10,200}", cid):
            raise ValueError("that does not look like a Google client ID (it ends "
                             "in .apps.googleusercontent.com)")
        doc, _why = _read_settings()
        doc["client_id"] = cid
        _write_settings(doc)
    if client_secret_value is not None:
        secret = str(client_secret_value).strip()
        if secret and not re.fullmatch(r"[A-Za-z0-9._-]{6,200}", secret):
            raise ValueError("that does not look like a Google client secret")
        if secret and not _write_secret(TARGET_CLIENT_SECRET, secret):
            raise ValueError("Windows Credential Manager refused to store the client "
                             "secret, so nothing was saved")
    return {"ok": True,
            "client_id_set": bool(client_id()),
            "client_secret_set": client_secret_present()}


# --------------------------------------------------------------------------
#   status - what the apps read, and never a token
# --------------------------------------------------------------------------

def _way_words(chosen: str, *, link: bool, signed_in: bool) -> str:
    """The status line's `way`, which must not call a saved thing "not set up".

    `mode` is still the separate fact: `connected` below is false while the
    chosen way is off, because Jarvis is not reading a calendar then. What this
    sentence fixes is the claim that nothing EXISTS - a saved iCal link or a
    saved Google sign-in is set up whether or not it has been chosen."""
    if chosen == "ical":
        return ("private link (read-only)" if link
                else "private link (read-only) - chosen, but no address saved")
    if chosen == "google":
        return ("Google sign-in (read/write)" if signed_in
                else "Google sign-in (read/write) - chosen, but not signed in")
    saved = []
    if link:
        saved.append("a private iCal link is saved")
    if signed_in:
        saved.append("a Google sign-in is saved")
    if saved:
        return "not chosen yet (" + " and ".join(saved) + ")"
    return "not set up"


def status() -> dict:
    """Plain words and booleans. NEVER a token, never part of one."""
    chosen = mode()
    flow = pending()
    with _LOCK:
        held = bool(_ACCESS.get("token"))
        expires_at = float(_ACCESS.get("expires_at") or 0.0)
        account = str(_ACCOUNT.get("name") or "")
    linked = bool(_ical_link())
    refresh = refresh_token_present()
    needs: list = []
    if chosen == "google":
        if not client_id():
            needs.append("the Google client ID")
        if not client_secret_present():
            needs.append("the Google client secret")
        if not refresh:
            needs.append("a Google sign-in")
    elif chosen == "ical":
        if not linked:
            needs.append("the private iCal address")
    elif not linked and not refresh:
        # With no way chosen, the Google client is only needed if the owner
        # picks the sign-in way; saying it is "still needed" would push one of
        # the two ways on someone who may want the private link.
        needs.append("a way chosen - mode ical (read-only) or mode google (read/write)")
    return {
        "mode": chosen,
        "connected": bool(chosen == "google" and refresh)
        or bool(chosen == "ical" and linked),
        "way": _way_words(chosen, link=linked, signed_in=refresh),
        "client_id": client_id(),          # public, and shown so it can be checked
        "client_id_set": bool(client_id()),
        "client_secret_set": client_secret_present(),
        "refresh_token_saved": refresh,
        "ical_link_saved": linked,
        "access_token_in_memory": held,
        "access_expires_at": expires_at,
        "account": account,
        "needs": needs,
        "flow": (flow.outcome() if flow is not None else {"outcome": "none"}),
        "read_only": chosen == "ical",
        "writes_need_a_card": True,
        "token_store": ("Windows Credential Manager, under \"" + TARGET_REFRESH + "\""
                        " - never a file, never the environment, never the phone"),
    }


# --------------------------------------------------------------------------
#   The chat sentences - deterministic, and each one is a fact
# --------------------------------------------------------------------------

_CONNECT = re.compile(
    r"(?i)\b(?:connect|link|set up|setup|hook up|add)\b.{0,40}\b(?:google\s+)?calendar\b"
    r"|\bcalendar\b.{0,30}\b(?:connect|link|set up|setup)\b")
_WHATSON = re.compile(
    r"(?i)\b(?:what'?s|what\s+is|whats)\s+(?:on|in)\s+my\s+(?:google\s+)?calendar\b"
    r"|\bmy\s+(?:google\s+)?calendar\s+(?:today|tomorrow|this\s+week)\b"
    r"|\b(?:any|what)\s+events?\s+(?:on|in)\s+my\s+calendar\b")
_ADD = re.compile(
    r"(?i)\b(?:add|put|schedule|create|book|set\s+up)\b.{0,30}\b(?:meeting|event|"
    r"appointment|call|lunch|dinner|reminder)\b")

_WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
             "friday": 4, "saturday": 5, "sunday": 6}
_TIME_RE = re.compile(r"(?i)\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b"
                      r"|\bat\s+(\d{1,2}):(\d{2})\b")
_DAY_RE = re.compile(r"(?i)\b(" + "|".join(_WEEKDAYS) + r")\b")
_TOMORROW_RE = re.compile(r"(?i)\btomorrow\b")
_TODAY_RE = re.compile(r"(?i)\btoday\b")
_FOR_RE = re.compile(r"(?i)\bfor\s+(\d{1,3})\s*(minutes?|mins?|hours?|hrs?)\b")
_TITLE_RE = re.compile(r"(?i)\b(?:add|put|schedule|create|book|set\s+up)\b\s+"
                       r"(?:a|an|the)?\s*(?:new\s+)?(meeting|event|appointment|"
                       r"call|lunch|dinner|reminder)\b")


def parse_meeting(text: str, *, now: Optional[datetime] = None) -> Optional[dict]:
    """The event the owner's words describe, or None.

    Deterministic on purpose, and narrow on purpose: a weekday (or "today" /
    "tomorrow") plus a clock time, with an optional "for 45 minutes". It never
    guesses a date it was not told - "sometime next week" gets None, and the
    chat answer asks which day rather than inventing one.
    """
    said = str(text or "")
    if not _ADD.search(said):
        return None
    moment = now or datetime.now().astimezone()
    if moment.tzinfo is None:
        moment = moment.astimezone()

    hour = minute = None
    for m in _TIME_RE.finditer(said):
        if m.group(1):
            hour, minute = int(m.group(1)), int(m.group(2) or 0)
            if m.group(3).lower() == "pm" and hour < 12:
                hour += 12
            if m.group(3).lower() == "am" and hour == 12:
                hour = 0
        else:
            hour, minute = int(m.group(4)), int(m.group(5))
        break
    if hour is None or not (0 <= hour <= 23 and 0 <= (minute or 0) <= 59):
        return None

    day = None
    weekday = _DAY_RE.search(said)
    if weekday:
        target = _WEEKDAYS[weekday.group(1).lower()]
        ahead = (target - moment.weekday()) % 7
        day = moment.date() + timedelta(days=ahead)
        candidate = datetime.combine(day, _time(hour, minute or 0), tzinfo=moment.tzinfo)
        if ahead == 0 and candidate <= moment:
            day = day + timedelta(days=7)      # "Tuesday" on a Tuesday evening
    elif _TOMORROW_RE.search(said):
        day = moment.date() + timedelta(days=1)
    elif _TODAY_RE.search(said):
        day = moment.date()
    if day is None:
        return None

    begin = datetime.combine(day, _time(hour, minute or 0), tzinfo=moment.tzinfo)
    span = timedelta(minutes=60)
    got = _FOR_RE.search(said)
    if got:
        amount = int(got.group(1))
        span = timedelta(hours=amount) if got.group(2).lower().startswith(("hour", "hr")) \
            else timedelta(minutes=amount)
    title = "Meeting"
    named = _TITLE_RE.search(said)
    if named:
        title = named.group(1).strip().capitalize()
    return {"summary": title[:120], "start": begin.isoformat(),
            "end": (begin + span).isoformat(),
            "where": "", "description": ""}


def connect_sentence() -> str:
    """The two real ways, and where each one lives. This is the answer that
    replaces the old "Jarvis cannot connect to external calendars".

    It reports what is SAVED as well as what is CHOSEN: a saved private iCal
    link with the chosen way still off is set up, and saying "neither is set up
    yet" to someone who pasted that link yesterday is simply wrong."""
    chosen = mode()
    linked = bool(_ical_link())
    signed_in = refresh_token_present()
    if chosen == "google" and signed_in:
        return ("Google Calendar is connected the read/write way: Google sign-in is "
                "the chosen way, so I can read your calendar and add, change or "
                "delete an event - each change waits for your yes on a card.")
    if chosen == "google" and not signed_in:
        return ("Google sign-in is the chosen way, but nobody has signed in on this PC "
                "yet. Run `py -3 jarvis_google_calendar.py connect` in the backend "
                "folder - the one-time Google Cloud setup is in " + SETUP_DOC + ".")
    if chosen == "ical" and linked:
        return ("Your calendar is connected the read-only way: the private iCal "
                "address. I can read it; I cannot add or change anything. Google "
                "sign-in is the other way if you want two-way - " + SETUP_DOC + ".")
    if chosen == "ical" and not linked:
        return ("The private iCal link is the chosen way, but no address is saved yet. "
                "Paste your calendar's secret iCal address (Google Calendar, Settings, "
                "the calendar, Integrate calendar) into the box in Settings, Accounts.")
    two_ways = (
        "Two ways, and only one is active at a time:\n\n"
        "1. Private link (read-only) - paste your calendar's secret iCal address "
        "(Google Calendar, Settings, the calendar, Integrate calendar) into the box "
        "that is already in Settings, Accounts. No sign-in, nothing else leaves this "
        "PC. I can read it, not change it.\n"
        "2. Google sign-in (read/write) - a one-time Google Cloud setup (about ten "
        "minutes, free), then one sign-in in your own browser. I can then read and "
        "add, change or delete an event, each change on an approval card.\n\n"
        "The Google setup and sign-in are commands in the backend folder today "
        "(the Settings window has no card for them yet): "
        "`py -3 jarvis_google_calendar.py client <client-id>`, then "
        "`py -3 jarvis_google_calendar.py connect`. The steps are in " + SETUP_DOC + ".")
    if linked and signed_in:
        return (two_ways + "\n\nBoth are already set up on this PC - the private link "
                "is saved and a Google sign-in is saved - but neither is chosen, so I "
                "am not reading your calendar. Choose one in the backend folder: "
                "`py -3 jarvis_google_calendar.py mode ical` (read-only) or "
                "`py -3 jarvis_google_calendar.py mode google` (read/write).")
    if linked:
        return (two_ways + "\n\nThe private iCal link is already saved, so only the "
                "choice is missing: `py -3 jarvis_google_calendar.py mode ical` in the "
                "backend folder turns it on (read-only).")
    if signed_in:
        return (two_ways + "\n\nA Google sign-in is already saved, so only the choice "
                "is missing: `py -3 jarvis_google_calendar.py mode google` in the "
                "backend folder turns it on (read/write).")
    return (two_ways + "\n\nNeither is set up yet. The Google setup and sign-in are "
            "the commands above; the private link needs no setup page at all.")


def answer(text: str, *, now: Optional[datetime] = None) -> Optional[str]:
    """The deterministic chat answer for one of the three calendar sentences,
    or None (so a caller can fall through to the model).

    Returns ONE STRING (the whole reply - one or two plain sentences), never a
    Result and never a dictionary - `jarvis_quick.answer()` returns
    `Optional[Result]`, so a caller that wires this in must wrap the reply (see
    WIRING at the top of this module).

    Reads are card-free; a proposed event is only PROPOSED here - nothing is
    sent to Google by this function, and no approval card is raised by it.
    Creating the event is a separate step, `create_event(parse_meeting(...))`,
    after the owner has said yes in chat.
    """
    said = str(text or "")
    if not said.strip():
        return None
    if _WHATSON.search(said):
        got = list_events(7, now=now)
        if not got.get("ok"):
            why = str(got.get("reason") or "").strip()
            if got.get("connected"):
                return why or "the calendar could not be read just now"
            if not why:
                return _NOT_CONNECTED_WORDS
            # SAY "NOT CONNECTED YET" ONCE. A reason that already says it (the
            # mode-off answer does) is the whole owner-facing reply; prefixing
            # it again is the B2 defect the phone field test of 2026-10-29 read
            # out as "Not connected yet - Google Calendar is not connected yet".
            return why if _SAYS_NOT_CONNECTED.search(why) else "Not connected yet - " + why
        rows = got.get("events") or []
        if not rows:
            return ("Nothing in your " + ("private iCal link" if got.get("read_only")
                                          else "Google Calendar") + " for the next "
                    + str(got.get("days", 7)) + " days.")
        lines = ["Your next " + str(got.get("days", 7)) + " days:"]
        for row in rows[:10]:
            when = row["start"] + ("" if row["all_day"] else " - " + row["end"][-5:])
            lines.append("- " + row["summary"] + ", " + when
                         + (", " + row["where"] if row["where"] else ""))
        if got.get("read_only"):
            lines.append("(Read from your private iCal link, which is read-only.)")
        return "\n".join(lines)
    if _ADD.search(said):
        proposed = parse_meeting(said, now=now)
        if proposed is None:
            return ("I can add that, but I need a day and a time - for example "
                    "\"add a meeting Tuesday 3pm\". Your calendar has to be connected "
                    "the Google sign-in way to add anything; the private link is "
                    "read-only.")
        if mode() != "google" or not refresh_token_present():
            return ("I would add \"" + proposed["summary"] + "\" on "
                    + proposed["start"] + " to " + proposed["end"] + ", but changing "
                    "a calendar needs the Google sign-in way - the private link is "
                    "read-only. " + connect_sentence())
        return ("I can add \"" + proposed["summary"] + "\" on " + proposed["start"]
                + " to " + proposed["end"] + ". It needs one approval card, and "
                "nothing is sent to Google until you say yes.")
    if _CONNECT.search(said):
        return connect_sentence()
    return None


# --------------------------------------------------------------------------
#   For the owner, in the backend folder - the one-time setup without a UI
# --------------------------------------------------------------------------
#
# The desktop's Settings window holds no door of its own to the backend (it
# has no token, and deliberately so), so every Settings card in this program
# is a Rust command. Adding one for this feature would mean editing
# `src-tauri/src/lib.rs`, which the parallel account-connect work is in, so
# the setup is these commands instead - the same shape `jarvis_token_store.py
# show` and `jarvis_chatbot_api.py key` already use. The routes below exist
# for whichever UI lands next; nothing here needs them.

def _usage() -> str:
    return (
        "Google Calendar, in the backend folder:\n"
        "    py -3 jarvis_google_calendar.py status\n"
        "    py -3 jarvis_google_calendar.py client <client-id>   (then paste the\n"
        "                                    client secret - it is not shown, and it\n"
        "                                    goes into Windows Credential Manager)\n"
        "    py -3 jarvis_google_calendar.py connect\n"
        "    py -3 jarvis_google_calendar.py mode off|ical|google\n"
        "    py -3 jarvis_google_calendar.py where\n"
        "    py -3 jarvis_google_calendar.py disconnect\n"
    )


def _main(argv, *, getpass_fn: Optional[Callable[[str], str]] = None) -> int:
    """The owner's own commands. Never prints a token; never reads one from a
    command line (a shell keeps its history)."""
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd not in ("status", "client", "connect", "mode", "where", "disconnect"):
        print(_usage())
        return 2
    if cmd == "status":
        st = status()
        print("Way:            " + st["way"])
        print("Connected:      " + ("yes" if st["connected"] else "no"))
        print("Client ID:      " + (st["client_id"] or "(not saved)"))
        print("Client secret:  " + ("saved" if st["client_secret_set"] else "(not saved)"))
        print("Refresh token:  " + ("saved" if st["refresh_token_saved"] else "(not saved)"))
        print("Kept in:        " + st["token_store"])
        if st["needs"]:
            print("Still needed:   " + ", ".join(st["needs"]))
        return 0
    if cmd == "where":
        print("Windows Credential Manager > Windows Credentials > \"" + TARGET_REFRESH + "\"")
        print("The client ID is in " + str(settings_path()) + " (it is not a secret).")
        return 0
    if cmd == "client":
        if len(argv) < 3 or not str(argv[2]).strip():
            print(_usage())
            return 2
        ask = getpass_fn
        if ask is None:
            try:
                import getpass as _getpass
                ask = _getpass.getpass
            except Exception:
                ask = None
        secret = ""
        if ask is not None:
            try:
                secret = ask("Paste the client secret (nothing is shown): ") or ""
            except (EOFError, KeyboardInterrupt):
                secret = ""
        try:
            out = set_client(argv[2], secret.strip() or None)
        except ValueError as exc:
            print(str(exc))
            return 1
        print("Client ID saved in " + str(settings_path()) + ".")
        print("Client secret: " + ("saved in Windows Credential Manager."
                                   if out["client_secret_set"] else "not saved."))
        print("Next: py -3 jarvis_google_calendar.py connect")
        return 0
    if cmd == "mode":
        try:
            out = set_mode(argv[2] if len(argv) > 2 else "")
        except ValueError as exc:
            print(str(exc))
            return 1
        print("Way: " + {"off": "off", "ical": "the private iCal link (read-only)",
                         "google": "Google sign-in (read/write)"}[out["mode"]])
        return 0
    if cmd == "connect":
        try:
            started = start()
        except FlowError as exc:
            print(str(exc))
            return 1
        print("Your browser should have opened Google's sign-in page.")
        if not started["browser_opened"]:
            print("It did not open by itself, so paste this into your browser "
                  "(it expires in ten minutes):")
            print("  " + started["auth_url"])
        print("Waiting for the sign-in to come back to this PC...")
        result = wait(FLOW_SECONDS + 30)
        outcome = result.get("outcome")
        if outcome == "connected":
            print("Connected. Windows Credential Manager now holds the token; the client")
            print("ID and the rest are in " + str(settings_path()) + ".")
            return 0
        print({
            "denied": "You (or Google) did not finish the sign-in. Nothing was saved.",
            "timed_out": "The sign-in window closed before the answer came back. "
                         "Nothing was saved - run connect again.",
            "cancelled": "Cancelled. Nothing was saved.",
            "exchange_failed": "Google refused the sign-in: "
                               + str(result.get("error") or "no reason given")
                               + " Nothing was saved.",
        }.get(outcome, "Nothing was saved (" + str(outcome) + ")."))
        return 1
    if cmd == "disconnect":
        print(disconnect()["message"])
        return 0
    return 2


if __name__ == "__main__":
    import sys as _sys
    raise SystemExit(_main(_sys.argv))


# --------------------------------------------------------------------------
#   The routes
# --------------------------------------------------------------------------

STATUS_PATH = "/api/google-calendar/status"
EVENTS_PATH = "/api/google-calendar/events"
UPDATE_PATH = "/api/google-calendar/events/update"
DELETE_PATH = "/api/google-calendar/events/delete"
START_PATH = "/api/google-calendar/start"
CANCEL_PATH = "/api/google-calendar/cancel"
DISCONNECT_PATH = "/api/google-calendar/disconnect"
MODE_PATH = "/api/google-calendar/mode"
CLIENT_PATH = "/api/google-calendar/client"

#: Every path this module answers. install() wraps only these; everything else
#: goes straight to the original handler, so nothing else about the server
#: changes.
ROUTES = (STATUS_PATH, EVENTS_PATH, UPDATE_PATH, DELETE_PATH, START_PATH,
          CANCEL_PATH, DISCONNECT_PATH, MODE_PATH, CLIENT_PATH)


def handle_get(route: str, query: str, *, transport: Optional[Callable] = None) -> tuple:
    if route == STATUS_PATH:
        return 200, status()
    if route == EVENTS_PATH:
        days = 7
        for key, value in parse_qsl(query or "", keep_blank_values=True):
            if key == "days":
                try:
                    days = int(value)
                except Exception:
                    days = 7
        return 200, list_events(days, transport=transport)
    return 404, {"ok": False, "error": "no such route"}


def handle_post(route: str, body: dict, *, transport: Optional[Callable] = None,
                gate=None, tier_of=None, spawn=None,
                opener: Optional[Callable[[str], Any]] = None) -> tuple:
    if route == START_PATH:
        try:
            return 200, dict(start(opener=opener, transport=transport), ok=True)
        except FlowError as exc:
            return 400, {"ok": False, "error": str(exc)}
    if route == CANCEL_PATH:
        return 200, {"ok": True, "cancelled": cancel()}
    if route == DISCONNECT_PATH:
        revoke = body.get("revoke", True) if isinstance(body, dict) else True
        return 200, disconnect(revoke=bool(revoke), transport=transport)
    if route == MODE_PATH:
        try:
            return 200, set_mode((body or {}).get("mode", ""))
        except ValueError as exc:
            return 400, {"ok": False, "error": str(exc)}
    if route == CLIENT_PATH:
        try:
            return 200, set_client((body or {}).get("client_id"),
                                   (body or {}).get("client_secret"))
        except ValueError as exc:
            return 400, {"ok": False, "error": str(exc)}
    if route == EVENTS_PATH:
        return create_event(body or {}, gate=gate, tier_of=tier_of, spawn=spawn,
                            transport=transport)
    if route == UPDATE_PATH:
        return update_event(body or {}, gate=gate, tier_of=tier_of, spawn=spawn,
                            transport=transport)
    if route == DELETE_PATH:
        return delete_event(body or {}, gate=gate, tier_of=tier_of, spawn=spawn,
                            transport=transport)
    return 404, {"ok": False, "error": "no such route"}


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_GET`/`do_POST` so the routes above are answered
    here, after the server's own origin and token checks. Every other request
    goes straight to the original - the same shape jarvis_vault.install and
    jarvis_antislop.install use, and the reason this feature needs no patch:
    `plugins/ready/google-calendar/plugin.json` names this module and
    jarvis_plugins.py makes the call a patch would have made.
    """
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(get0, "_jarvis_google_calendar", False):
        return "  calendar   Google Calendar (already on)"

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
        parts = urlsplit(str(getattr(self, "path", "") or ""))
        route = parts.path.rstrip("/")
        if route not in ROUTES:
            return get0(self)
        if not _allowed(self):
            return None
        try:
            code, out = handle_get(route, parts.query)
        except Exception as exc:
            # The exception's NAME only: its message can carry a URL.
            code, out = 503, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    def do_POST(self):
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route not in ROUTES:
            return post0(self)
        if not _allowed(self):
            return None
        try:
            body = json.loads(read_body(self) or b"{}")
        except Exception as exc:
            return self._send(400, {"ok": False, "error": type(exc).__name__})
        if not isinstance(body, dict):
            return self._send(400, {"ok": False, "error": "the request must be a JSON object"})
        try:
            code, out = handle_post(route, body)
        except Exception as exc:
            code, out = 503, {"ok": False, "outcome": "failed",
                              "error": type(exc).__name__,
                              "message": LAST_WORDS["failed"]}
        return self._send(code, out)

    do_GET._jarvis_google_calendar = True
    do_POST._jarvis_google_calendar = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    chosen = mode()
    return ("  calendar   Google Calendar: "
            + {"off": "neither way chosen yet - mode ical or mode google in the "
                      "backend folder",
               "ical": "the private iCal link (read-only)",
               "google": ("Google sign-in (read/write)" if refresh_token_present()
                          else "Google sign-in chosen but not signed in")}[chosen])
