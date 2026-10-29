"""jarvis_connect_account.py - "connect my calendar" / "set up github", with ONE
card that takes the value and puts it in Windows Credential Manager.

WHY THIS EXISTS, IN THE OWNER'S WORDS (2026-10-28)

    "in regards to the calendar AUDits I meant to check if other features of
    jarvis can be connected to my accounts through chat and if I need to put in
    a password a notification will pop up or if I need to put in a USername and
    a password. it should be able to connect all features just through me
    talking to jarvis"

The answer he got instead was *"jarvis cannot connect directly to external
calendars ... Would you like instructions on exporting your calendar to ICS?"* -
false about Jarvis (it reads CalDAV and a private iCal link today) and useless
to him. The storage half was already right; what was missing was the join:
"connect X" -> one card -> Credential Manager -> one real test.

WHAT IT IS, AND IS NOT

This module is the SERVICE TABLE and the CARD STATE MACHINE for connecting one
account, plus the one real test per service. It holds no UI, opens no route by
itself (the host half is `jarvis_connect_account_wiring.py`) and writes nothing
except through `jarvis_token_store.store_secret` - Credential Manager, and
nowhere else.

Two doors raise the same card, so the model is never the one answering:

  * `jarvis_agent.py`'s `connect_account` tool (when the model is offered it);
  * `jarvis_quick.py`'s deterministic grammar ("connect my calendar", "set up
    github"), which needs no model at all and is the reason a refusal cannot
    happen again.

WHAT IS NEVER DONE, AND EACH IS TESTED

  * No value is ever returned by this module. `raise_card`, `pending_cards`,
    `status`, `status_words` and every receipt carry the service, the field
    NAMES, the store entry NAMES and the verify verdict - never a value. The
    one function that sees a value is `save_card`, which hands it straight to
    `store_secret` and to the verifier and keeps no copy (Python cannot wipe
    memory; see the honest limits below).
  * There is no plaintext fallback. If Credential Manager refuses, the receipt
    says so and NOTHING is written to a file, an environment variable, a
    database, a log or the clipboard. The whole point of the store is that a
    value that cannot go in it is not kept at all.
  * Nothing is saved from the chat. The only writer is the card, answered on
    this PC; the phone has no card to type into and no route to reach.
  * A verifier that fails is never reported as connected. "Saved, and GitHub
    accepted it" and "saved, but the link answered HTTP 404" are different
    sentences and the code cannot produce the first from the second.

HONEST LIMITS, SAID PLAINLY

  * Python cannot wipe a string from memory. A value lives for the duration of
    one `save_card` call, is not copied into any structure this module keeps,
    and is never written anywhere but Credential Manager. It is not a secure
    enclave, and Credential Manager is readable by any program running as the
    same Windows user (jarvis_token_store.py:17-21 says the same).
  * An environment variable still WINS over the store (`resolve_secret`'s own
    order - "someone who set it meant it"). An owner who already exported
    `JARVIS_CALDAV_PASSWORD` would see a card that appears to do nothing, so
    every receipt and every status answer names the source that is winning.
  * CalDAV's ADDRESS is not a secret and is not on this card: it lives in
    Settings, Accounts (`accounts.json`, jarvis_accounts.py), and the CalDAV
    test says so when it is missing rather than guessing one.
  * The verifiers make ONE request each, bounded (see VERIFY_TIMEOUT_S), and
    report only its status - never a body. GitHub's is `GET /user`, CalDAV's is
    one `PROPFIND` on the saved address, iCal's is one `GET` of the private
    link.
"""
from __future__ import annotations

import base64
import collections
import json
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional, Tuple

#: How long the owner has to fill in a connect card and submit it. Shorter
#: than a session, longer than reading a Settings page for a link.
CARD_TTL_S = 300.0
#: Most connect cards pending at once. A card is per service, so this is far
#: more than a person can use; the bound exists so a loop cannot grow memory.
MAX_PENDING_CARDS = 8
#: A value longer than this is refused rather than truncated - the same limit
#: the owner-secret hand-off uses for a secret it types.
MAX_VALUE_CHARS = 4096
#: One verifier request, and how much of its answer is read. Only the status
#: (and GitHub's own login name) is ever reported.
VERIFY_TIMEOUT_S = 10.0
VERIFY_MAX_BYTES = 64 * 1024
#: The model's own "what I want this for" text is untrusted; it is cleaned,
#: capped and shown to the owner as a note, never as fact.
MAX_LABEL_CHARS = 100

_CARD_ID_PREFIX = "ca_"


class ConnectAccountError(Exception):
    """Something about a connection was refused, in words safe to show."""


class ConnectAccountVoided(ConnectAccountError):
    """That card is unknown, used or expired; nothing was saved."""


# --------------------------------------------------------------------------
#   The service table
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Field:
    """One box on the card. `name` is what the page posts back and is the ONLY
    key the save route accepts; `kind` only decides how the box is drawn and
    whether the page masks it."""

    name: str
    label: str
    kind: str                      # "url" | "username" | "password" | "token"
    hint: str = ""

    @property
    def secret(self) -> bool:
        """Whether the page masks the box. A username is not a secret, but it
        is still never sent to the model, so every field here is typed on the
        PC and left there."""
        return self.kind in ("password", "token")


@dataclass(frozen=True)
class Service:
    """One thing the owner can connect, and everything the card has to say.

    `words` is the closed vocabulary both doors resolve against - the tool's
    `service` argument and the quick path's sentence. `fields` is the card's
    whole surface. `store` is the field->Credential Manager entry map, filled
    in by `targets()` so the module imports the owning modules lazily (this
    module is importable on a PC without a calendar, exactly like the rest)."""

    id: str
    name: str
    words: Tuple[str, ...]
    fields: Tuple[Field, ...]
    summary: str
    note: str = ""
    how: str = ""                  # the one sentence "not connected yet" adds
    verify: str = ""               # "ics" | "caldav" | "github"


SERVICES: "collections.OrderedDict[str, Service]" = collections.OrderedDict([
    ("calendar_ics", Service(
        id="calendar_ics",
        name="Calendar - the private iCal link",
        words=("calendar ics", "ical", "ics", "private calendar link", "private link",
               "google calendar", "outlook calendar", "external calendar",
               "published calendar", "calendar"),
        fields=(Field(
            name="url",
            label="Private iCal link (the \"Secret address in iCal format\")",
            kind="url",
            hint=("In Google Calendar on a computer: the gear, Settings, your calendar, "
                  "Integrate calendar, then copy the Secret address in iCal format. "
                  "Any calendar that gives you a private .ics address works the same."),
        ),),
        summary=("Jarvis reads this calendar itself, read-only, on this PC. No Google "
                 "sign-in and no permission grant is involved."),
        note=("The link is handled like a password: it is typed here, on this PC, and "
              "kept in Windows Credential Manager - never in the chat."),
        how=("Say \"connect my calendar\" and one card appears for the private iCal link, "
             "or \"connect my CalDAV calendar\" for a server's username and password."),
        verify="ics",
    )),
    ("calendar_caldav", Service(
        id="calendar_caldav",
        name="Calendar - a CalDAV server (username and password)",
        words=("caldav", "nextcloud", "radicale", "baikal", "fastmail", "icloud",
               "apple calendar", "owncloud", "calendar server"),
        fields=(
            Field(name="username", label="CalDAV username", kind="username"),
            Field(name="password", label="CalDAV password", kind="password",
                  hint=("If your provider gives you an app password for calendar apps "
                        "(Fastmail, Nextcloud and iCloud do), use that one, not your "
                        "login password.")),
        ),
        summary=("Jarvis reads this calendar itself, read-only, on this PC, with the "
                 "same username and password a calendar app uses."),
        note=("The server ADDRESS is not a secret and is not asked for here: it is in "
              "Settings, Accounts, under Calendar address. Set it there first if it is "
              "empty - the test below says so rather than guessing one."),
        how=("Say \"connect my CalDAV calendar\" and one card appears for the username and "
             "password."),
        verify="caldav",
    )),
    ("github", Service(
        id="github",
        name="GitHub (a personal access token)",
        words=("github", "git hub", "github token", "github account", "github access token"),
        fields=(Field(
            name="token",
            label="GitHub personal access token",
            kind="token",
            hint=("On github.com: Settings, Developer settings, Personal access tokens, "
                  "then create one. A read-only token is enough for private repositories "
                  "and CI watching."),
        ),),
        summary=("Jarvis uses this token for GitHub searches, private repositories and "
                 "CI watches. It is sent to api.github.com and nowhere else."),
        note=("The token is handled like a password: typed here, on this PC, and kept "
              "in Windows Credential Manager - never in the chat."),
        how="Say \"connect GitHub\" and one card appears for a personal access token.",
        verify="github",
    )),
])

#: The service each store target belongs to, for a status sentence that can say
#: where a value is coming from. Filled in by `targets()`.
_UNSET = object()


def targets(service_id: str) -> Dict[str, str]:
    """field name -> the Credential Manager entry that holds it.

    The entries themselves belong to the modules that read them (the same rule
    every other named secret follows: "every caller passes its OWN target"), so
    they are looked up here rather than copied. A PC without one of those
    modules gets a clear refusal for that service and the other two still
    work."""
    if service_id == "calendar_ics":
        import jarvis_calendar
        return {"url": jarvis_calendar.ICS_URL_TARGET}
    if service_id == "calendar_caldav":
        import jarvis_calendar
        return {"username": jarvis_calendar.USER_TARGET,
                "password": jarvis_calendar.PASSWORD_TARGET}
    if service_id == "github":
        import jarvis_research
        return {"token": jarvis_research.TOKEN_TARGET}
    raise ConnectAccountError("there is no such service to connect")


def env_names(service_id: str) -> Dict[str, str]:
    """field name -> the environment variable that still wins over the store."""
    if service_id in ("calendar_ics", "calendar_caldav"):
        import jarvis_calendar
        if service_id == "calendar_ics":
            return {"url": jarvis_calendar.ICS_URL_ENV}
        return {"username": jarvis_calendar.USER_ENV,
                "password": jarvis_calendar.PASSWORD_ENV}
    if service_id == "github":
        import jarvis_research
        return {"token": jarvis_research.TOKEN_ENV}
    raise ConnectAccountError("there is no such service to connect")


def service(service_id: str) -> Service:
    got = SERVICES.get(str(service_id or "").strip())
    if got is None:
        raise ConnectAccountError(
            "I can connect " + ", ".join(s.name for s in SERVICES.values()) + ".")
    return got


def service_from_words(text: object) -> Optional[str]:
    """The service a person's (or the model's) words name, or None.

    Whole-word matching against the closed list above, longest phrase first, so
    "google calendar" lands on the private link and a bare "calendar" does too -
    and "connect my email" deliberately returns None, because email is not on
    this card yet (Phase 2). Returning None is what makes the answer honest
    instead of a card for something that cannot be verified.
    """
    words = " ".join(str(text or "").lower().split())
    if not words:
        return None
    best = None
    for sid, svc in SERVICES.items():
        for phrase in svc.words:
            # A whole word, or its plural: the owner's own sentence says
            # "external calendars like google or outlook", not "calendar".
            m = re.search(r"\b" + re.escape(phrase) + r"s?\b", words)
            if m is None:
                continue
            # EARLIEST first (a sentence that names two services connects the one
            # it named first), then the longest phrase at that place, so "google
            # calendar" beats a bare "calendar" and "github token" beats "github".
            at = m.start()
            if best is None or at < best[0] or (at == best[0] and len(phrase) > best[1]):
                best = (at, len(phrase), sid)
    return best[2] if best else None


def clean_label(label: object) -> str:
    """The model's own note, made safe to show as untrusted text."""
    out = []
    for ch in str(label or ""):
        out.append(" " if (ord(ch) < 0x20 or ord(ch) == 0x7F) else ch)
    return " ".join("".join(out).split())[:MAX_LABEL_CHARS]


# --------------------------------------------------------------------------
#   The card
# --------------------------------------------------------------------------

@dataclass
class _Pending:
    card_id: str
    service_id: str
    label: str
    created: float


_PENDING: "collections.OrderedDict[str, _Pending]" = collections.OrderedDict()
_LOCK = threading.RLock()


def _prune_locked(now: float) -> None:
    stale = [cid for cid, p in _PENDING.items() if (now - p.created) > CARD_TTL_S]
    for cid in stale:
        _PENDING.pop(cid, None)
    while len(_PENDING) > MAX_PENDING_CARDS:
        _PENDING.popitem(last=False)


def card_view(p: _Pending) -> dict:
    """What the HUD draws. NO value can appear here, and none exists yet.

    The field NAMES are the save route's whole accepted vocabulary; the labels
    and hints are the host's own words (from the table above), and the model's
    note is in its own field, marked untrusted."""
    svc = SERVICES[p.service_id]
    return {
        "kind": "connect_account",
        "card_id": p.card_id,
        "service": svc.id,
        "service_label": svc.name,
        "summary": svc.summary,
        "note": svc.note,
        "fields": [{"name": f.name, "label": f.label, "kind": f.kind,
                    "secret": f.secret, "hint": f.hint} for f in svc.fields],
        "agent_claimed_note": p.label,
        "agent_note_is_untrusted": True,
        "stores_where": "Windows Credential Manager, on this PC",
        "store_entries": list(targets(svc.id).values()),
        "from_this_pc_only": True,
        "expires_in_seconds": int(CARD_TTL_S),
    }


def raise_card(service_id: str, label: object = "", *,
               clock: Callable[[], float] = time.time) -> dict:
    """Raise ONE connect card for one service, and return the card's view.

    Called by the model's `connect_account` tool and by `jarvis_quick.py`'s
    sentence grammar - one implementation, two doors, so the two can never
    describe the connection differently. Raising a card approves nothing: a
    value exists only after the owner types it on this PC and submits.
    """
    svc = service(service_id)
    now = clock()
    with _LOCK:
        _prune_locked(now)
        # One card per service: asking again replaces the old one rather than
        # stacking two boxes for the same account.
        for cid in [c for c, p in _PENDING.items() if p.service_id == svc.id]:
            _PENDING.pop(cid, None)
        if len(_PENDING) >= MAX_PENDING_CARDS:
            raise ConnectAccountError(
                "Too many connect cards are already waiting; finish or cancel one first.")
        card_id = _CARD_ID_PREFIX + secrets.token_hex(12)
        p = _Pending(card_id=card_id, service_id=svc.id,
                     label=clean_label(label), created=now)
        _PENDING[card_id] = p
    return card_view(p)


def pending_cards(*, clock: Callable[[], float] = time.time) -> list:
    """Cards waiting for the owner, newest first, metadata only (no value)."""
    now = clock()
    with _LOCK:
        _prune_locked(now)
        out = []
        for p in list(_PENDING.values()):
            view = card_view(p)
            view["expires_in_seconds"] = max(0, int(CARD_TTL_S - (now - p.created)))
            out.append(view)
    out.sort(key=lambda v: v["expires_in_seconds"])
    return out


def cancel_card(card_id: str) -> bool:
    """The owner pressed Cancel. True when there was one to drop."""
    with _LOCK:
        return _PENDING.pop(str(card_id or ""), None) is not None


# --------------------------------------------------------------------------
#   Saving, and the one real test per service
# --------------------------------------------------------------------------

def _check_url(field_name: str, value: str) -> str:
    """One sentence for an address that is not one Jarvis may send a value to,
    or "" when it is fine. A private link is https (or plain http only inside
    the owner's own networks - jarvis_local_http's rule, security audit L7)."""
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme == "webcal":
        return "that link starts with webcal:// - change it to https:// and try again"
    if parsed.scheme not in ("https", "http"):
        return f"the {field_name} must be an https:// address"
    if not parsed.hostname:
        return f"the {field_name} has no host in it"
    if parsed.username or parsed.password:
        return f"the {field_name} has a user name or password inside it - copy it again"
    if parsed.scheme == "http":
        try:
            import jarvis_local_http
            problem = jarvis_local_http.plain_http_problem(value, "", "the link")
            if problem:
                return problem
        except Exception:                   # noqa: BLE001 - module absent: https only
            return f"the {field_name} must be an https:// address"
    return ""


def _request(method: str, url: str, *, headers=None, data: Optional[bytes] = None,
             auth: Optional[Tuple[str, str]] = None,
             timeout: float = VERIFY_TIMEOUT_S,
             max_bytes: int = VERIFY_MAX_BYTES) -> Tuple[int, str]:
    """ONE bounded request. Returns (status, at most `max_bytes` of the body).

    Every verifier goes through this function, so the rules are in one place:
    the timeout is fixed, the read is capped, redirects are not followed (a
    redirect could carry the value to another host - the same rule
    `jarvis_calendar._RefuseRedirect` enforces for the calendar), and a
    non-2xx answer is returned as its status rather than raised, so a refusal
    is reported as a status and never as an error string that could echo
    anything.

    Tests replace `_REQUEST` with a stand-in; nothing else in this module opens
    a socket.
    """
    req = urllib.request.Request(url, data=data, method=method,
                                 headers=dict(headers or {}))
    if auth is not None and auth[0]:
        raw = f"{auth[0]}:{auth[1]}".encode("utf-8")
        req.add_header("Authorization",
                       "Basic " + base64.b64encode(raw).decode("ascii"))
    try:
        import jarvis_local_http
        opener = jarvis_local_http.opener_for(url, _NoRedirect)
    except Exception:                       # noqa: BLE001 - module absent
        opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req, timeout=timeout) as r:
            status = int(getattr(r, "status", 0) or 0)
            body = r.read(max_bytes) or b""
    except urllib.error.HTTPError as exc:
        return int(exc.code), ""
    except Exception:                       # noqa: BLE001 - network failure
        return 0, ""
    if isinstance(body, str):
        return status, body
    return status, body.decode("utf-8", "replace")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is refused: it could carry the value to another host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None


#: Tests replace this with a stand-in `(method, url, headers, data, auth, timeout,
#: max_bytes) -> (status, body)`. Nothing else opens a socket.
_REQUEST: Optional[Callable[..., Tuple[int, str]]] = None


def _http(method: str, url: str, **kwargs) -> Tuple[int, str]:
    if _REQUEST is not None:
        return _REQUEST(method, url, **kwargs)
    return _request(method, url, **kwargs)


def verify(service_id: str, values: Dict[str, str]) -> Tuple[bool, str]:
    """One real test of one service, with the values that will actually be used.

    Returns `(connected, sentence)`. Never raises, and never puts a value in the
    sentence - only the service's own status words."""
    try:
        if service_id == "calendar_ics":
            return _verify_ics(values)
        if service_id == "calendar_caldav":
            return _verify_caldav(values)
        if service_id == "github":
            return _verify_github(values)
        return False, "there is no test for that service yet"
    except ConnectAccountError as exc:
        return False, str(exc)
    except Exception as exc:                # noqa: BLE001 - the NAME only
        return False, f"the test could not run ({type(exc).__name__})"


def _verify_ics(values: Dict[str, str]) -> Tuple[bool, str]:
    url = str(values.get("url") or "")
    if not url:
        return False, "no private calendar link is saved yet"
    try:
        import jarvis_calendar
        problem = jarvis_calendar._feed_problem(url)
    except Exception:                       # noqa: BLE001 - module absent
        problem = _check_url("private link", url)
    if problem:
        return False, problem
    status, body = _http("GET", url, headers={"User-Agent": "jarvis-connect-account"})
    if status == 0:
        return False, ("the private link could not be reached from this PC "
                       "(no answer, or a redirect was refused)")
    if status != 200:
        return False, f"the private link answered HTTP {status}"
    if "BEGIN:VCALENDAR" not in body.upper():
        return False, ("the link answered, but it is not a calendar feed (it has no "
                       "BEGIN:VCALENDAR in it)")
    return True, "the private link answered and it is a real calendar feed (read-only)"


def _verify_caldav(values: Dict[str, str]) -> Tuple[bool, str]:
    user = str(values.get("username") or "")
    password = str(values.get("password") or "")
    if not user or not password:
        return False, "both the CalDAV username and password are needed"
    try:
        import jarvis_accounts, jarvis_calendar
        url = jarvis_calendar._base_url()
    except Exception:                       # noqa: BLE001 - module absent
        return False, "the calendar module is not on this PC, so CalDAV cannot be tested"
    if not url:
        return False, ("no CalDAV address is saved yet - put it in Settings, Accounts, "
                       "under Calendar address first (the address is not a secret)")
    try:
        import jarvis_local_http
        problem = jarvis_local_http.plain_http_problem(url, jarvis_calendar.URL_ENV,
                                                      "the calendar password")
    except Exception:                       # noqa: BLE001
        problem = ""
    if problem:
        return False, problem
    body = (b'<?xml version="1.0" encoding="utf-8"?>'
            b'<d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype/></d:prop></d:propfind>')
    status, _text = _http("PROPFIND", url, auth=(user, password),
                          data=body,
                          headers={"Depth": "0",
                                   "Content-Type": "application/xml; charset=utf-8"})
    if status == 0:
        return False, ("the CalDAV address could not be reached from this PC "
                       "(no answer, or a redirect was refused)")
    if status == 401:
        return False, "the CalDAV server refused that username and password (HTTP 401)"
    if status == 403:
        return False, "the CalDAV server refused that account (HTTP 403)"
    if status not in (200, 207):
        return False, f"the CalDAV server answered HTTP {status}"
    return True, "the CalDAV server accepted the username and password (one PROPFIND)"


def _verify_github(values: Dict[str, str]) -> Tuple[bool, str]:
    token = str(values.get("token") or "")
    if not token:
        return False, "no GitHub token is saved yet"
    status, body = _http(
        "GET", "https://api.github.com/user",
        headers={"Accept": "application/vnd.github+json",
                 "User-Agent": "jarvis-connect-account",
                 "X-GitHub-Api-Version": "2022-11-28",
                 "Authorization": f"Bearer {token}"})
    if status == 0:
        return False, "api.github.com could not be reached from this PC"
    if status in (401, 403):
        return False, (f"GitHub refused that token (HTTP {status}; a 403 can also mean "
                       "the rate limit was hit from this address)")
    if status != 200:
        return False, f"GitHub answered HTTP {status}"
    login = ""
    try:
        login = str((json.loads(body) or {}).get("login") or "")
    except Exception:                       # noqa: BLE001 - an unreadable body is fine
        login = ""
    return True, ("GitHub accepted the token" +
                  (f" (signed in as {login})" if login else ""))


# --------------------------------------------------------------------------
#   Saving
# --------------------------------------------------------------------------

def _resolved(service_id: str) -> Dict[str, str]:
    """The values the FEATURE will use right now, by field name - the
    environment variable first, then the store (resolve_secret's own order)."""
    out = {}
    for name, env in env_names(service_id).items():
        target = targets(service_id)[name]
        import jarvis_token_store
        out[name] = jarvis_token_store.resolve_secret(env, target)
    return out


def _winning_source(service_id: str) -> Dict[str, str]:
    import os
    out = {}
    for name, env in env_names(service_id).items():
        out[name] = "environment" if os.environ.get(env, "").strip() else "credential-manager"
    return out


def save_card(card_id: str, values: object, *,
              clock: Callable[[], float] = time.time) -> dict:
    """Save ONE card's values into Credential Manager, then run its real test.

    The order is the security property:
      1. the card is looked up (unknown/expired/used consumes nothing);
      2. the VALUES are checked against the card's own field names - an unknown
         key is refused by name, a missing or empty one is refused by label,
         and every value is length-capped. Nothing here echoes a value;
      3. the card is consumed (one submit, ever);
      4. each value goes to `jarvis_token_store.store_secret` - Credential
         Manager and NOWHERE else. A failure stops here, reports the store
         entry that refused, and saves nothing further: there is no plaintext
         fallback of any kind;
      5. the test runs with the values the feature will actually use (an
         environment variable still wins, and the receipt says so);
      6. the receipt names the store entries, the source that won and the
         verdict - never a value.
    """
    cid = str(card_id or "")
    now = clock()
    with _LOCK:
        _prune_locked(now)
        p = _PENDING.get(cid)
    if p is None:
        raise ConnectAccountVoided(
            "That connect card is unknown, used or expired; nothing was saved.")
    svc = SERVICES[p.service_id]
    if (now - p.created) > CARD_TTL_S:
        cancel_card(cid)
        raise ConnectAccountVoided("That connect card expired; nothing was saved.")
    if not isinstance(values, dict):
        raise ConnectAccountError(
            "The card sends one object of field name to value; nothing was saved.")
    allowed = {f.name: f for f in svc.fields}
    extra = [str(k) for k in values if str(k) not in allowed]
    if extra:
        raise ConnectAccountError(
            "That card only takes " + ", ".join(sorted(allowed)) +
            "; nothing was saved.")
    clean: Dict[str, str] = {}
    for name, f in allowed.items():
        raw = values.get(name)
        text = raw if isinstance(raw, str) else ""
        if not text.strip():
            raise ConnectAccountError(
                f"The {f.label} box is empty; nothing was saved.")
        if len(text) > MAX_VALUE_CHARS:
            raise ConnectAccountError(
                f"The {f.label} is longer than {MAX_VALUE_CHARS} characters; "
                "nothing was saved.")
        clean[name] = text
    # The card is spent exactly once, before anything is written.
    cancel_card(cid)

    import jarvis_token_store
    entries = targets(svc.id)
    saved = []
    for name, text in clean.items():
        try:
            jarvis_token_store.store_secret(entries[name], text)
        except jarvis_token_store.StoreError as exc:
            raise ConnectAccountError(
                f'Windows Credential Manager refused to save "{entries[name]}" '
                f'({exc}). Nothing else was written: there is no other place '
                "Jarvis keeps a value, so this one is not saved at all.") from None
        saved.append(entries[name])

    source = _winning_source(svc.id)
    try:
        in_use = _resolved(svc.id)
    except Exception:                       # noqa: BLE001 - module absent
        in_use = dict(clean)
    ok, said = verify(svc.id, in_use)
    overridden = sorted(n for n, src in source.items() if src == "environment")
    receipt = {
        "ok": True,
        "service": svc.id,
        "service_label": svc.name,
        "saved_to": saved,
        "verified": bool(ok),
        "verify_words": said,
        "source": source,
        "environment_wins_for": overridden,
        "needs_pc": True,
    }
    if overridden:
        names = sorted(env_names(svc.id)[n] for n in overridden)
        receipt["note"] = (
            "Saved. " + " and ".join(names) + " is set in this PC's environment and "
            "still WINS over what was just saved - clear it (and start Jarvis again) "
            "to use this value instead.")
    return receipt


# --------------------------------------------------------------------------
#   Status the chat can read
# --------------------------------------------------------------------------

def status(*, probe: bool = True, clock: Callable[[], float] = time.time) -> list:
    """Every service, whether it is set up, and - when asked - whether it works.

    `connected` is only ever True after the service's own verifier passed, so a
    saved-but-broken link reads as "saved, but ..." and never as connected.
    `probe=False` answers from the store alone (no socket), for a caller that
    must not wait.
    """
    out = []
    for sid, svc in SERVICES.items():
        try:
            values = _resolved(sid)
            entries = targets(sid)
        except Exception as exc:            # noqa: BLE001 - module absent
            out.append({"service": sid, "name": svc.name, "configured": False,
                        "connected": False,
                        "words": f"{svc.name}: not available on this PC "
                                 f"({type(exc).__name__})",
                        "environment_wins_for": []})
            continue
        configured = all(bool(values.get(f.name)) for f in svc.fields)
        source = _winning_source(sid)
        overridden = [env_names(sid)[n] for n, s in source.items() if s == "environment"]
        if not configured:
            out.append({"service": sid, "name": svc.name, "configured": False,
                        "connected": False, "words": "",
                        "environment_wins_for": overridden,
                        "store_entries": list(entries.values())})
            continue
        ok, said = verify(sid, values) if probe else (False, "")
        out.append({"service": sid, "name": svc.name, "configured": True,
                    "connected": bool(ok), "detail": said,
                    "environment_wins_for": overridden,
                    "store_entries": list(entries.values())})
    return out


def status_of(service_id: str, *, probe: bool = True) -> dict:
    for row in status(probe=probe):
        if row["service"] == service_id:
            return row
    raise ConnectAccountError("there is no such service to connect")


def status_words(service_id: str, *, probe: bool = True) -> str:
    """ONE or two plain sentences the chat can say about one service.

    This is the "is my calendar connected?" answer: it is built from the store
    and from a real test, never from a guess, and it names the source that is
    winning when an environment variable shadows what was saved."""
    try:
        row = status_of(service_id, probe=probe)
    except ConnectAccountError as exc:
        return str(exc)
    svc = SERVICES[service_id]
    if not row.get("configured"):
        return (f"{svc.name}: not connected yet. " + (svc.how or
                "Ask me to connect it and one card will take the value on this PC."))
    if not probe:
        return f"{svc.name}: saved in Credential Manager, not tested just now."
    if row.get("connected"):
        said = f"{svc.name}: connected - {row.get('detail') or 'the test passed'}."
    else:
        said = (f"{svc.name}: saved, but it did not work just now - "
                f"{row.get('detail') or 'the test did not pass'}. Nothing is reading it "
                "until that works.")
    if row.get("environment_wins_for"):
        said += (" The value in use comes from " +
                 " and ".join(row["environment_wins_for"]) +
                 " in this PC's environment, which wins over the saved one.")
    return said


def reset_for_tests() -> None:
    """Drop every pending card. Tests only; never called in production."""
    with _LOCK:
        _PENDING.clear()


__all__ = [
    "CARD_TTL_S", "MAX_PENDING_CARDS", "MAX_VALUE_CHARS", "VERIFY_TIMEOUT_S",
    "ConnectAccountError", "ConnectAccountVoided", "Field", "Service", "SERVICES",
    "targets", "env_names", "service", "service_from_words", "clean_label",
    "raise_card", "pending_cards", "cancel_card", "card_view", "save_card",
    "verify", "status", "status_of", "status_words", "reset_for_tests",
]
