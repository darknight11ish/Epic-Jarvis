"""jarvis_accounts.py - the ADDRESSES of the owner's accounts, and the one
settings file they live in. Never a secret.

WHY THIS EXISTS (the owner's decision of 2026-10-06, CLAUDE.md: "anything
needing a key or a sign-in should be settable in the Jarvis app itself,
desktop only, stored under rule 3")

The desktop's Settings -> Accounts card already collects four SECRETS: the
IMAP username, the IMAP password, the private calendar link and the Home
Assistant token. It collected no server ADDRESS, so email could not work from
the app at all - `jarvis_email.plan()` answered "JARVIS_IMAP_HOST is not set -
there is no mail server to read" - and Home Assistant answered "not set up on
this PC". The addresses were settable only as plain-text Windows environment
variables.

TWO SHAPES, AND AN ADDRESS IS THE SECOND ONE (both already code-proven here)

  * A SECRET (a key, a password, a token, the private iCal link) goes into
    Windows Credential Manager, written by the desktop's own Rust, and never
    over HTTP: `jarvis_token_store.resolve_secret` (ease-of-use audit row 15),
    the desktop's `token_store.rs`, Settings -> Accounts. This module holds
    none of them and refuses to.
  * An ADDRESS or a CHOICE goes to a backend route that keeps it in a
    plain-text JSON file in the config folder and hands it back to the UI.
    The proven model is the SearXNG address: `jarvis_search.settings_path()`
    = `<config>/web-search.json` with `handle_settings({"searxng_url": ...})`,
    and the desktop's `web_search.rs` posting to `/api/search/settings`.

    There is a code-proven reason NOT to put an address in Credential Manager:
    a store-sourced value is registered with jarvis_scrub and redacted BY
    EXACT VALUE, which would swallow harmless surrounding text such as a host
    name (backend/test_account_secrets.py, its own first bullet). So an
    address is a small `accounts.json` beside `web-search.json`, and this
    module is that file's one reader and writer.

THE EIGHT, AND NOTHING ELSE

    imap_host, imap_port, imap_mailbox      how Jarvis reads the inbox
    smtp_host, smtp_port, smtp_tls          how it sends one email
    home_url                                the owner's Home Assistant
    caldav_url                              their calendar, the CalDAV way

`smtp_tls` is the one CHOICE rather than an address ("ssl", "starttls" or
"off"); it is stored and read exactly the same way, because a choice has the
same shape as an address and the same problem with Credential Manager.

THE ENVIRONMENT VARIABLE STILL WINS, ALWAYS (value(), below)

Every one of the eight is set today as a Windows environment variable, and an
installation that already sets one keeps working exactly as before: `value()`
reads the variable first and the file only as the fallback. The file can never
override, shadow or clear a variable the owner set, and saving here never
touches one. This is the same backward-compatibility guarantee
`jarvis_token_store.resolve_secret` makes for the four secrets.

WHAT THIS MODULE NEVER DOES
  - It never reads or writes a key, a password, a token or the private iCal
    link, and `handle_settings()` REFUSES a request that carries one by name
    (CLAUDE.md rule 3): nothing here can put a secret in a plain-text file.
  - It never echoes back what it was sent on a refusal, and no error message
    carries a value.
  - It never opens a socket, and it never checks whether an address answers -
    an address is checked for SHAPE only (and, for plain `http://`, for being
    on the owner's own networks - `jarvis_local_http.plain_http_problem`'s
    own rule, reused, never re-invented).

Standard library only. Opens nothing on import.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.parse
from pathlib import Path

#: The eight addresses and choices the Accounts card collects, in the order
#: the card shows them. A SECRET is deliberately not one of these.
FIELDS = (
    "imap_host",
    "imap_port",
    "imap_mailbox",
    "smtp_host",
    "smtp_port",
    "smtp_tls",
    "home_url",
    "caldav_url",
)

#: field -> the environment variable that names it today, which still WINS on
#: every read (value()). Kept here rather than in each reader so the mapping
#: has one home; `env_or_file()` is the same table the other way round.
ENV = {
    "imap_host": "JARVIS_IMAP_HOST",
    "imap_port": "JARVIS_IMAP_PORT",
    "imap_mailbox": "JARVIS_IMAP_MAILBOX",
    "smtp_host": "JARVIS_SMTP_HOST",
    "smtp_port": "JARVIS_SMTP_PORT",
    "smtp_tls": "JARVIS_SMTP_TLS",
    "home_url": "JARVIS_HOME_URL",
    "caldav_url": "JARVIS_CALDAV_URL",
}

_BY_ENV = {name: key for key, name in ENV.items()}

#: The three ways an email may travel - the SAME list as
#: jarvis_email_send.TLS_MODES, and a test checks the two agree, so a fourth
#: mode added there cannot be silently unsettable here.
TLS_MODES = ("ssl", "starttls", "off")

#: An address, a port and a mailbox name are short. A longer one is a paste
#: mistake, not an address.
MAX_CHARS = 200

_WHY_UNREADABLE = ("the account addresses file could not be read, so the addresses saved in "
                   "it are not being used. Type them again in Settings, Accounts, to "
                   "rewrite it")


# --------------------------------------------------------------------------
#   The file: <config folder>/accounts.json, beside web-search.json
# --------------------------------------------------------------------------

def _config_dir() -> Path:
    """The same folder the rest of the backend uses, found the same way
    (jarvis_search._config_dir, which this deliberately mirrors - the two
    files must sit side by side)."""
    fw = sys.modules.get("jarvis_framework")
    if fw is None:
        try:
            import jarvis_framework as fw  # type: ignore
        except Exception:
            fw = None
    if fw is not None:
        try:
            return Path(fw.CONFIG_DIR)
        except Exception:
            pass
    env = os.environ.get("OPENJARVIS_CONFIG_DIR")
    if env:
        return Path(os.path.expanduser(env))
    return Path(os.path.expanduser("~")) / ".openjarvis"


def addresses_path() -> Path:
    return _config_dir() / "accounts.json"


_LOCK = threading.Lock()


def addresses() -> dict:
    """Every one of the eight, as text, plus "why".

    Text on purpose: each value is used in exactly the place
    `os.environ.get(<the variable>)` used to be, so a number is stored as the
    digits the owner typed ("993", not 993) and an empty string means "not set
    here" - the environment variable, if the owner has one, still wins.

    No file: all eight are "" and "why" is "" - simply nothing saved here yet,
    which is what every installation has today.

    A damaged or unreadable file fails SAFE, not closed: all eight read as ""
    (so nothing is ever read from a file nobody can parse - an address is
    never guessed at) and "why" says so in plain words. It does NOT refuse the
    reads: these are addresses the owner typed, and every reader already has
    its own true sentence for an address that is not set."""
    doc, why = _read()
    out = {key: "" for key in FIELDS}
    for key in FIELDS:
        value = doc.get(key, "")
        out[key] = value.strip() if isinstance(value, str) else ""
    out["why"] = why
    return out


def _read() -> tuple:
    """(the file as a dict, why it could not be used). ({},"") when there is
    no file at all."""
    try:
        raw = addresses_path().read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}, ""
    except OSError:
        return {}, _WHY_UNREADABLE
    try:
        doc = json.loads(raw)
        if not isinstance(doc, dict):
            raise ValueError
    except Exception:
        return {}, _WHY_UNREADABLE
    return doc, ""


def _save(**changes) -> dict:
    """Write the eight, with `changes` applied, atomically (a temporary file
    then a replace, so a half-written file is never read). An OSError is
    raised for the caller to put into words."""
    with _LOCK:
        cur = addresses()
        new = {key: cur[key] for key in FIELDS}
        new.update(changes)
        new["changed"] = time.time()
        path = addresses_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(new), encoding="utf-8")
        os.replace(tmp, path)
    return addresses()


# --------------------------------------------------------------------------
#   Reading: the environment variable first, the file only as the fallback
# --------------------------------------------------------------------------

def env_set(key: str) -> bool:
    """Whether the owner already set this one as a Windows environment
    variable, which WINS on every read. Whether only, never its value: the
    page shows where a value comes from, never what an environment variable
    holds (backend/test_account_secrets.py's own rule for the four secrets)."""
    name = ENV.get(key)
    return bool(name and str(os.environ.get(name, "") or "").strip())


def value(key: str) -> str:
    """`key`'s value in force: the environment variable if the owner set one,
    else what is saved in accounts.json, else "".

    The one place the "the environment variable still wins" rule lives - every
    reader below calls this rather than reading either source itself."""
    if env_set(key):
        return str(os.environ.get(ENV[key], "") or "").strip()
    return addresses().get(key, "")


def env_or_file(env_name: str) -> str:
    """The same thing, asked the way a module that reads an environment
    variable by name has to ask it (jarvis_reach.py's `_env`). "" for a name
    that is not one of the eight - so a secret's own name can never be
    answered from this file."""
    key = _BY_ENV.get(str(env_name or "").strip())
    return value(key) if key else ""


# --------------------------------------------------------------------------
#   Checking one value before it is saved
# --------------------------------------------------------------------------

def address_problem(key: str, value_in) -> str:
    """"" when `value_in` may be saved under `key`, else the plain sentence
    saying why not. NEVER returns or echoes the value in an error: an address
    is not a secret, but a mistake pasted into the wrong box might be one, and
    an error message is not a place to reproduce it.

    Shape only - nothing is looked up, nothing is dialled, and a plain
    `http://` address is judged by jarvis_local_http's own rule (this PC, the
    home network, Tailscale or NordVPN Meshnet), reused rather than
    re-invented."""
    if key not in ENV:
        return "that is not one of the account addresses"
    text = str(value_in if value_in is not None else "").strip()
    if not text:
        return ""                      # "" means "not set here" - allowed
    if len(text) > MAX_CHARS:
        return "it is too long to be an address, a port or a mailbox name"
    if key in ("imap_host", "smtp_host"):
        return _server_problem(text)
    if key in ("imap_port", "smtp_port"):
        return _port_problem(text)
    if key == "smtp_tls":
        if text.lower() not in TLS_MODES:
            return (f"it must be one of {', '.join(TLS_MODES)} - how the email is "
                    f"encrypted on its way out")
        return ""
    return _url_problem(key, text)


def _server_problem(text: str) -> str:
    """A mail server name or address, and nothing else.

    The check is jarvis_email_send's own `_host_ok` - the one the sending
    module already applies to a host it was handed - reused rather than
    written a second time. If that module is not here, this FAILS CLOSED: an
    address nobody can check is not saved."""
    ok = False
    try:
        import jarvis_email_send as ES
        ok = bool(ES._host_ok(text))
    except Exception:
        ok = False
    if not ok:
        return ("it is not a plain mail server name or address (no http://, no port "
                "on the end, no /path)")
    return ""


def _port_problem(text: str) -> str:
    try:
        port = int(text)
    except (TypeError, ValueError):
        return "it is not a port number"
    if not 1 <= port <= 65535:
        return "a port number is between 1 and 65535"
    return ""


def _url_problem(key: str, text: str) -> str:
    """A web address for Home Assistant or the calendar: `http` or `https`,
    with a host, and - for plain `http://` - only on the owner's own networks.
    That last rule is jarvis_local_http.plain_http_problem's, the rule the
    Home Assistant and calendar reads already enforce, asked here so the
    owner is told at the box rather than later on a failed read."""
    try:
        parts = urllib.parse.urlsplit(text)
        parts.port                        # raises ValueError for a bad port
        scheme, host = parts.scheme.lower(), parts.hostname or ""
    except ValueError:
        return "that address could not be read"
    if scheme not in ("http", "https"):
        return "it must start with http:// or https://"
    if not host:
        return "it needs a host name (for example http://homeassistant.local:8123)"
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        return "it must not have a user name or password written into it"
    try:
        import jarvis_local_http as LH
    except Exception:
        return ("the address cannot be checked on this PC (jarvis_local_http.py is "
                "missing), so it was not saved")
    secret = ("your Home Assistant token" if key == "home_url"
              else "your calendar password")
    why = LH.plain_http_problem(text, ENV[key], secret)
    if why:
        return why
    return ""


# --------------------------------------------------------------------------
#   The route's own words
# --------------------------------------------------------------------------

#: Said on any request that names something other than the eight. It never
#: repeats what was sent: a field name is not a secret, but a value pasted
#: into the wrong box might be, and this sentence is the point rather than a
#: diagnostic.
REFUSES_SECRETS = (
    "this route takes an ADDRESS only - one of " + ", ".join(FIELDS) + ". A key, a "
    "password, a token or the private calendar link is never sent here: it is typed on "
    "this PC and kept in Windows Credential Manager, so nothing carried by this "
    "connection can put a secret in a plain-text file"
)

_ONE_AT_A_TIME = ("send exactly one of " + ", ".join('{"%s": ...}' % f for f in FIELDS))


def view() -> dict:
    """What GET /api/accounts/addresses answers: the eight, in FIELDS' order,
    each with its environment variable's name and whether that variable is set
    on this PC. An environment variable's VALUE is never in here - only
    whether one wins."""
    doc = addresses()
    return {
        "available": True,
        "why": doc.get("why", ""),
        "fields": [
            {
                "name": key,
                "env": ENV[key],
                "env_set": env_set(key),
                "value": doc.get(key, ""),
            }
            for key in FIELDS
        ],
    }


def handle_get() -> tuple:
    return 200, view()


def handle_settings(body) -> tuple:
    """POST /api/accounts/addresses - ONE change per request:

       {"imap_host": "imap.gmail.com"}     immediate
       {"smtp_tls": "starttls"}            immediate
       {"home_url": ""}                    immediate; "" puts it back to
                                           "not set here" (an environment
                                           variable, if any, still wins)

    An ADDRESS or a CHOICE only. A request naming anything else - a key, a
    password, a token, the private iCal link, or any name this file does not
    know - is refused with REFUSES_SECRETS, and NOTHING is written. Matches
    jarvis_search.handle_settings' own "one change per request" shape; the
    refusal is stronger, because here the whitelist IS the security rule."""
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "the request must be a JSON object"}
    named = [k for k in body if k in ENV]
    refused = [k for k in body if k not in ENV]
    if refused:
        return 400, {"ok": False, "error": REFUSES_SECRETS}
    if len(named) != 1:
        return 400, {"ok": False, "error": _ONE_AT_A_TIME}
    key = named[0]
    raw = body[key]
    if raw is None or isinstance(raw, (dict, list, bool)):
        return 400, {"ok": False, "error": f"{key} must be text"}
    text = str(raw).strip()
    why = address_problem(key, text)
    if why:
        return 400, {"ok": False, "error": f"That {key} cannot be used: {why}."}
    try:
        _save(**{key: text})
    except OSError:
        # The owner's own words, never the operating system's: a settings box
        # must say what to do, not print an errno.
        return 503, {"ok": False,
                     "error": ("the settings file on this PC could not be written, so "
                               "nothing was saved. Check that the Jarvis config folder "
                               "can be written to, then try again.")}
    said = (f"Cleared the {key} saved here." if not text
            else f"Saved {key} = {text} on this PC.")
    return 200, {"ok": True, "said": said, **view()}
