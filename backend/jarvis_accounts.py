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


# ==========================================================================
#   THE ACCOUNTS JARVIS CAN USE - appended 2026-11-03
# ==========================================================================
#
# WHY THIS EXISTS (the owner's ask, verbatim): "i also want jarvis to be able
# to explain what accounts are actively connected to jarvis, what permissions
# and abilities jarvis has for those accounts, whats changeable, how to
# disconnect the account, and how to connect new accounts that jarvis can
# control or use".
#
# The code ABOVE answers one narrow half of that: the eight ADDRESSES the
# desktop's Settings, Accounts card collects. This half is the inventory the
# owner actually asked for - one row per account family, the exact Windows
# Credential Manager entry NAMES (never a value), the permission each action
# really has (read LIVE from jarvis_framework and jarvis_gate, never copied
# here), what can be changed and where, how to disconnect, and which things
# are deliberately not accounts at all.
#
# WHAT THIS HALF NEVER DOES
#   - It never returns a value, a mask, a prefix, a length or a third party's
#     error sentence. Entry NAMES only.
#   - It never opens a socket on the default path. `probe=False` is the only
#     mode the route uses; `probe=True` is a future explicit "test it now",
#     and it goes through the owning module's own verifier
#     (jarvis_connect_account.status(probe=True),
#     jarvis_google_calendar.status()) - never a hand-rolled request.
#   - It never invents a tier and never invents the word "never": when the
#     permission table cannot be read on this PC, `tier` is None, `asks` is
#     None and the row's `why` says so.
#   - It never guesses when an account was connected. Credential Manager keeps
#     no timestamp, so `connected_at` is always None and `connected_at_known`
#     always False.
#   - It imports every other backend module INSIDE a function, so this module
#     still imports on a PC that is missing any of them.
#
# WHY THE TWO NEW NAMES ARE NOT `view` AND `handle_get`
#
# The contract first asked for `view()` and `handle_get(query="")` with the
# family list. THIS MODULE ALREADY HAD BOTH - they are the shipped
# GET /api/accounts/addresses answer (accounts.patch calls
# `jarvis_accounts.handle_get()` and test_account_addresses.py asserts its
# "fields"). Appending same-named functions would shadow them, and a shipped
# route answering a second shape is exactly the quiet breakage this module
# avoids. So the family list has its OWN names - `accounts_view()` and
# `handle_accounts_get()` - and `view` / `handle_get` above stay the addresses
# answer, byte-untouched. The contract was amended 2026-11-03 to say so.

from dataclasses import dataclass
from typing import Optional, Tuple

import re


#: The read-only route the host layer serves. One path, no query, never a
#: probe (contract section 6). `jarvis_connect_account_wiring.py` owns the
#: route itself; this module answers it.
OVERVIEW_PATH = "/api/accounts"

#: The page's own title, shared by the desktop plate, the phone plate and
#: /api/self (contract section 7.2) so three screens cannot drift apart.
_TITLE = "The accounts Jarvis can use"

#: The PROSE for each machine state. The state VALUE stays one of the four
#: `_STATE_*` strings; only the sentence changes.
_STATE_CONNECTED = "connected"
_STATE_SAVED = "saved"
_STATE_NOT_SET_UP = "not_set_up"
_STATE_NOT_AN_ACCOUNT = "not_an_account"

_STATE_WORDS = {
    _STATE_CONNECTED: "connected",
    _STATE_SAVED: "saved on this PC, not tested just now",
    _STATE_NOT_SET_UP: "not set up",
    _STATE_NOT_AN_ACCOUNT: "not an account",
}

#: jarvis_framework's four tiers, in the one order jarvis_asks_first.SAYS uses.
#: An answer outside this tuple is NOT trusted as a tier (see `abilities`).
_TIERS = ("auto", "notify", "ask", "never")

#: How much of a tier is left when jarvis_framework cannot be read at all. The
#: row must SAY that rather than guess (contract section 4).
_PERMISSION_UNREADABLE = ("the permission table could not be read on this PC, so what "
                          "this action asks first is not known")

#: Said when the gate (jarvis_gate) cannot be read: the tier may still be
#: known, but what the action risks is not.
_GATE_UNREADABLE = ("the gate's action table could not be read on this PC, so what this "
                    "action risks is not known")


@dataclass(frozen=True)
class Family:
    """One account family: everything the five answers need, in one place.

    A NAME is not a value. `store_entries` holds Windows Credential Manager
    ENTRY NAMES (what the store is asked for), never anything the store holds;
    `address_keys` names the eight non-secret addresses in this module's FIELDS;
    `env_names` are the environment variables that still WIN over both. The
    words are the closed vocabulary `account_from_words` resolves against, so a
    new family with no words is simply unreachable by chat - and a test can see
    that.
    """

    id: str
    name: str
    # "card" | "settings" | "cli" | "folder" | "not_an_account"
    kind: str
    words: Tuple[str, ...]         # closed vocabulary for account_from_words
    store_entries: Tuple[str, ...]   # Credential Manager ENTRY NAMES, never values
    address_keys: Tuple[str, ...]    # names in this module's FIELDS
    env_names: Tuple[str, ...]       # environment variables that still win
    abilities: Tuple[str, ...]       # gate action ids, resolved LIVE
    verify: str                    # "connect_account:<id>" | "google" | "none"
    change: str                    # one sentence: where a change is made
    remove: str                    # one sentence: how to disconnect / why not
    limit: str                     # the honest caveat, "" if none
    can: str                       # one sentence: what Jarvis can DO with it


#: The twelve families, in the order the answer lists them. See the comment
#: against each FACTS field for where that exact string was read from - none of
#: them is guessed, and a test compares every entry name against the constant
#: the owning module exports.
FAMILIES: Tuple[Family, ...] = (
    Family(
        id="calendar_ics",
        name="Your calendar (private iCal link)",
        kind="card",
        words=("calendar", "ical", "ical link", "private link", "calendar link"),
        # jarvis_calendar.ICS_URL_TARGET
        store_entries=("Jarvis Backend/Calendar iCal link",),
        address_keys=(),
        # jarvis_calendar.ICS_URL_ENV
        env_names=("JARVIS_CALENDAR_ICS_SECRET_URL",),
        abilities=("calendar_read",),
        verify="connect_account:calendar_ics",
        change='Settings > Accounts, or say "connect my calendar"',
        remove=("Remove it in Settings > Accounts - the same box it was typed into."),
        limit=("Read-only: Jarvis can read your events and change nothing. Anyone "
               "with this link can read the calendar."),
        can="Read your events.",
    ),
    Family(
        id="calendar_caldav",
        name="Your calendar (CalDAV sign-in)",
        kind="card",
        words=("caldav", "caldav sign-in", "calendar sign-in"),
        # jarvis_calendar.USER_TARGET, jarvis_calendar.PASSWORD_TARGET
        store_entries=("Jarvis Backend/CalDAV username",
                       "Jarvis Backend/CalDAV password"),
        address_keys=(),
        # jarvis_calendar.USER_ENV, PASSWORD_ENV, and URL_ENV (the CalDAV
        # address; the contract puts it in this tuple rather than in
        # address_keys, and jarvis_calendar.login() reads it from here).
        env_names=("JARVIS_CALDAV_USER", "JARVIS_CALDAV_PASSWORD", "JARVIS_CALDAV_URL"),
        abilities=("calendar_read",),
        verify="connect_account:calendar_caldav",
        change='Say "connect my calendar with CalDAV"',
        remove=("Not removable from any screen yet: the connect card created these two "
                "entries and the next slice adds a Remove button. Until then they can "
                "be removed by hand in Windows Credential Manager."),
        limit="Read-only.",
        can="Read your events.",
    ),
    Family(
        id="google_calendar",
        name="Google Calendar (read and write)",
        kind="cli",
        words=("google calendar", "google", "gmail calendar", "google sign-in"),
        # jarvis_google_calendar.TARGET_CLIENT_SECRET, TARGET_REFRESH
        store_entries=("Jarvis Backend/Google Calendar client secret",
                       "Jarvis Backend/Google Calendar refresh token"),
        address_keys=(),
        # jarvis_google_calendar reads no environment variable for either: the
        # client id is a plain setting and the two secrets are store-only.
        env_names=(),
        # jarvis_google_calendar.ACTION_WRITE - the ONE gate action every event
        # write is asked under (jarvis_google_calendar.py:1343).
        abilities=("google_calendar_write",),
        verify="google",
        change=("One-time on this PC: py -3 jarvis_google_calendar.py client, then mode "
                "google, then connect. Steps: docs/GOOGLE-CALENDAR-SETUP.md"),
        remove=("py -3 jarvis_google_calendar.py disconnect - it also asks Google to "
                "forget the permission (Google's own record is at "
                "myaccount.google.com/permissions)."),
        limit=("Read AND write: every change to an event asks you first on one card."),
        can=("Read your events, and add, change or delete one after you say yes."),
    ),
    Family(
        id="github",
        name="GitHub",
        kind="card",
        words=("github",),
        # jarvis_research.TOKEN_TARGET
        store_entries=("Jarvis Backend/GitHub token",),
        address_keys=(),
        # jarvis_research.TOKEN_ENV
        env_names=("JARVIS_GITHUB_TOKEN",),
        # The FULL surface, named the way the gate and jarvis_agent.TOOLS name
        # it. The old pair here (`github_read`, `research_authenticated`) was
        # the 2026-09-30 research-and-watch surface; it kept saying "Read-only"
        # for four days after the owner's 2026-11-03 "Read + actions" decision
        # added the three carded actions (2026-11-07 audit, BLOCKER 3: this row
        # was the one place `/api/accounts` still described the old surface).
        # The four reads share `github_inspect`; the eleven carded writes each
        # have their own action in the shipped [autonomy.tiers] - the three of
        # 2026-11-03, the one CREATE of 2026-11-09, the merge and fix-and-push of
        # 2026-11-10, and the five of the same day's 22:30 ruling's Step 2
        # (open a pull request, workflow, labels, edit, review). Every one is
        # carded and can never be auto-approved.
        abilities=("github_inspect", "github_comment", "github_open_issue",
                   "github_rerun_workflow", "github_create_repo", "github_merge_pr",
                   "github_fix_and_push", "github_open_pr", "github_workflow",
                   "github_issue_labels", "github_edit_pr", "github_pr_review",
                   "github_issue_state", "github_read",
                   "research_authenticated"),
        verify="connect_account:github",
        change=('Say "connect my GitHub" for the token card, then switch each '
                'GitHub tool on in Settings, What asks first, under "Let the AI '
                'use this" (group "Jarvis\'s own tools")'),
        remove=("Not removable from any screen yet - the next slice adds a Remove "
                "button; until then only by hand in Windows Credential Manager. Jarvis "
                "forgetting it does not revoke it: the token stays valid on github.com "
                "until you delete it there. Switching the sixteen tools off in Settings, "
                "What asks first, stops it being used without deleting the token."),
        limit=("Read AND act, each with its own card: five read tools (list, "
               "read-file, CI status, the pull request cockpit and one pull request "
               "in full) and eleven actions "
               "(comment, open an issue, re-run a workflow, create one new empty "
               "repository on your own account, merge ONE pull request with a merge "
               "commit pinned to the head commit the card showed, push a fix to a "
               "pull request's own branch, open a pull request for a new branch, "
               "cancel or re-run one workflow run, change the labels on one issue, "
               "edit one pull request's title/body, and post one review that is "
               "never an approval). It can never force-push, squash, rebase, approve, "
               "close an issue, dispatch a workflow, bypass a required check, push "
               "to main/master/release/* or delete/close a repository or branch."),
        can=("Read your repositories, open pull requests, issues, CI status and one "
             "file, scan the pull requests that can be merged, read one pull request "
             "in full, and comment, open an issue, re-run a workflow, create one new "
             "empty repository, merge one pull request with a merge commit, push a "
             "fix to a pull request's own branch, open a pull request, cancel or "
             "re-run a run, change labels, edit a pull request's text or post a "
             "review - each after you say yes on its own card; never a force-push, "
             "a squash, a rebase, an admin bypass, an approval or a delete."),
    ),
    Family(
        id="email",
        name="Email (IMAP and SMTP)",
        kind="settings",
        words=("email", "mail", "imap", "inbox", "smtp"),
        # jarvis_email.IMAP_USER_TARGET, IMAP_PASSWORD_TARGET
        store_entries=("Jarvis Backend/IMAP username", "Jarvis Backend/IMAP password"),
        address_keys=("imap_host", "imap_port", "imap_mailbox",
                      "smtp_host", "smtp_port", "smtp_tls"),
        # jarvis_email.USER_ENV, PASSWORD_ENV
        env_names=("JARVIS_IMAP_USER", "JARVIS_IMAP_PASSWORD"),
        abilities=("email_read", "draft_email", "send_email"),
        verify="none",
        change=("Settings > Accounts: four secrets, and the mail-server addresses in "
                "the same place."),
        remove=("There is no disconnect for email as an account. Clear the boxes in "
                "Settings > Accounts, and clear the addresses there; an environment "
                "variable that is set still wins."),
        limit=('Jarvis has no tester for a mail server, so "set up" is not "working" - '
               'it is only "the details are saved".'),
        can=("Read your inbox; write a draft; send one email only after you say yes."),
    ),
    Family(
        id="home_assistant",
        name="Home Assistant",
        kind="settings",
        words=("home assistant", "home automation", "lights", "plugs"),
        # jarvis_home.TOKEN_TARGET
        store_entries=("Jarvis Backend/Home Assistant token",),
        address_keys=("home_url",),
        # jarvis_home.TOKEN_ENV
        env_names=("JARVIS_HOME_TOKEN",),
        # home_read is jarvis_home's read action; home_control is the write one
        # (jarvis_gate._TOOL_ACTIONS maps jarvis_home_control_run to it, and the
        # tier table has it at "ask").
        abilities=("home_read", "home_control"),
        verify="none",
        change="Settings > Accounts: the token, and the Home Assistant address.",
        remove=("There is no disconnect as an account. Clear the token box in Settings "
                "> Accounts; an environment variable that is set still wins."),
        limit=('No tester either: "set up" means the details are saved, not that the '
               'address answers.'),
        can="Read states; switch a light or plug only after you say yes.",
    ),
    Family(
        id="search_keys",
        name="Web search keys",
        kind="settings",
        words=("search", "web search", "search key", "search keys"),
        # jarvis_search.KEY_TARGETS (the four providers that need a key;
        # searxng and duckduckgo need none)
        store_entries=("Jarvis Backend/Exa key", "Jarvis Backend/Tavily key",
                       "Jarvis Backend/Brave Search key",
                       "Jarvis Backend/DeepSeek Search key"),
        address_keys=(),
        # No environment variable names a search key: jarvis_search.py reads
        # only OPENJARVIS_CONFIG_DIR from the environment.
        env_names=(),
        abilities=("search_the_web", "read_web_page"),
        verify="none",
        change=("Settings > Web search: one box per search provider, and Remove beside "
                "each."),
        remove=("Remove each key in Settings > Web search. A key is never shown back, "
                "only whether one is saved."),
        limit="A saved key is not a tested key.",
        can=("Search the web, and read one page, through the provider whose key is "
             "saved."),
    ),
    Family(
        id="chatbot_keys",
        name="Cloud AI keys",
        kind="settings",
        words=("cloud ai", "chatbot", "chatbot key", "api key"),
        # jarvis_chatbot_api.KEY_TARGETS, one per PRESETS entry:
        # OpenAI, DeepSeek, Mistral AI, xAI, OpenRouter and Groq.
        store_entries=("Jarvis Backend/OpenAI API key",
                       "Jarvis Backend/DeepSeek API key",
                       "Jarvis Backend/Mistral AI API key",
                       "Jarvis Backend/xAI API key",
                       "Jarvis Backend/OpenRouter API key",
                       "Jarvis Backend/Groq API key"),
        address_keys=(),
        # No environment variable names a cloud key either: jarvis_chatbot_api.py
        # reads only OPENJARVIS_CONFIG_DIR / JARVIS_CONFIG_DIR from the
        # environment.
        env_names=(),
        # UNVERIFIED: no gate action id governs USING a cloud key. The only
        # action a cloud escalation raises a card under is
        # jarvis_presets.CLOUD_ACTION = "change_own_config", and that is the
        # card for turning the cloud lane on or off - a settings change, not
        # an ability of the keys - so it is deliberately NOT listed here as
        # if it were one. jarvis_chatbot_api has no gate call at all, and
        # [autonomy.tiers] has no cloud-send line (only chatbot_session and
        # quiz_cloud_grade, neither of which is this). Left () and reported.
        abilities=(),
        verify="none",
        change="Settings > Cloud AI: one box per service, and Remove beside each.",
        remove="Remove each key there; a key is never shown back.",
        limit="Only used when you choose a cloud lane; the everyday model is local.",
        can="Only if you ask for a cloud lane.",
    ),
    Family(
        id="vault",
        name="Saved credentials (the blind vault)",
        kind="settings",
        words=("vault", "saved credentials", "saved password"),
        # The entry names here are the owner's own vault names and come from
        # jarvis_vault.handles() at read time (never a value), so the Family
        # carries no fixed entry names.
        store_entries=(),
        address_keys=(),
        env_names=(),
        abilities=(),
        verify="none",
        change=("The vault's own screen when it is built; today `vault` is filled by "
                "asking Jarvis to remember a credential at the service that uses it."),
        remove=("Forget one by name: it goes when the name is forgotten; the VALUE is "
                "never shown back."),
        limit="Names only - never a value, a mask or a prefix.",
        can=("Use a saved credential at the one service it is bound to, and nowhere "
             "else."),
    ),
    Family(
        id="notes",
        name="Your notes folder",
        kind="folder",
        words=("notes", "obsidian", "logseq", "joplin", "vault folder"),
        store_entries=(),
        address_keys=(),
        env_names=(),
        # jarvis_notes_edit.ACTION ("edit_vault_note") is the gate action one
        # save is asked under; jarvis_notes_search_run -> notes_search for the
        # read (jarvis_gate._TOOL_ACTIONS).
        abilities=("notes_search", "edit_vault_note"),
        verify="none",
        change="Settings > Folders: the folder Jarvis may read and add to.",
        remove=("Nothing to disconnect: a folder is not an account. Point Settings > "
                "Folders at another folder to stop using this one."),
        limit="The notes are files on this PC, not an account.",
        can="Search your notes, and add a note.",
    ),
    Family(
        id="notion",
        name="Notion",
        kind="not_an_account",
        words=("notion",),
        store_entries=(),
        address_keys=(),
        env_names=(),
        abilities=(),
        verify="none",
        change=("Nothing to connect: Notion is a one-time export you import into your "
                "notes vault."),
        remove=("Nothing to disconnect: there is no Notion account connected to "
                "Jarvis."),
        limit="Jarvis has no Notion sign-in; files in, files out.",
        can="Import a Notion export into your vault.",
    ),
    Family(
        id="spotify_drive_dropbox",
        name="Spotify, Google Drive and Dropbox",
        kind="not_an_account",
        words=("spotify", "google drive", "dropbox", "drive"),
        store_entries=(),
        address_keys=(),
        env_names=(),
        abilities=(),
        verify="none",
        change=("Not connected and not connectable: Jarvis has no sign-in for these. A "
                "sentence asking about them says so."),
        remove="Nothing to disconnect.",
        limit="Nothing here promises these can be connected.",
        can="Nothing - and Jarvis says so instead of pretending.",
    ),
)


# --------------------------------------------------------------------------
#   The small, safe readers every row is built from
# --------------------------------------------------------------------------

def _family(account_id: object) -> Optional[Family]:
    """The family with this id, or None. Never raises, never echoes the id."""
    key = str(account_id or "").strip()
    for fam in FAMILIES:
        if fam.id == key:
            return fam
    return None


def _backend(name: str):
    """That backend module if this PC has it, else None.

    Imported HERE rather than at the top of the file (contract section 2), so
    this module still imports on a PC missing any of the modules it describes.
    """
    try:
        return __import__(name)
    except Exception:                       # noqa: BLE001 - a missing module is a fact
        return None


def _env_set(name: str) -> bool:
    """Whether an environment variable is set to something. Never its value."""
    return bool(name and str(os.environ.get(str(name), "") or "").strip())


def _settings_value(key: str) -> str:
    """One of the eight addresses in force (environment first, then the file).

    `value()` above is the one place that rule lives, so it is reused rather
    than read a second way here.
    """
    try:
        return str(value(key) or "")
    except Exception:                       # noqa: BLE001 - an unreadable file is ""
        return ""


def _store_has(target: str) -> bool:
    """Whether a Credential Manager entry is saved. Existence only.

    Credential Manager has no "does this name exist" call: reading is the only
    way to tell, and the value is used ONLY for its truthiness and dropped
    inside this function. It never reaches a row, a sentence, a log line or an
    error, and nothing is ever written.
    """
    try:
        import jarvis_token_store
    except Exception:                       # noqa: BLE001 - no store module, no entries
        return False
    try:
        store = jarvis_token_store.default_store(str(target))
    except Exception:                       # noqa: BLE001 - an unopenable store is empty
        return False
    if isinstance(store, getattr(jarvis_token_store, "StoreError", ())):
        return False
    try:
        return bool(str(store.read() or "").strip())
    except Exception:                       # noqa: BLE001 - an unreadable entry is empty
        return False


def _vault_names(ctx: dict) -> list:
    """The NAMES the vault holds, once per call (jarvis_vault.handles())."""
    if ctx.get("vault") is None:
        names = []
        try:
            import jarvis_vault
            for row in jarvis_vault.handles() or []:
                name = str((row or {}).get("name") or "").strip()
                if name:
                    names.append(name)
        except Exception:                   # noqa: BLE001 - no vault module, no names
            names = []
        ctx["vault"] = names
    return list(ctx["vault"])


def _notes_folder(ctx: dict) -> str:
    """The notes folder the owner configured, or "" (jarvis_notes.obsidian_vault)."""
    if ctx.get("notes") is None:
        folder = ""
        try:
            import jarvis_notes
            got = jarvis_notes.obsidian_vault()
            folder = str(got) if got else ""
        except Exception:                   # noqa: BLE001 - no module, not configured
            folder = ""
        ctx["notes"] = folder
    return str(ctx["notes"])


def _configured(fam: Family, ctx: dict) -> bool:
    """Whether anything at all is set up for this family (contract section 5).

    "Configured" is NOT "working": a card family with an entry saved, or an
    environment variable set, counts; a settings family counts once any part of
    it is saved (a key, an address, a token); the vault once it holds a name;
    the notes folder once a folder is set. The row's own sentence never calls
    any of this "connected".
    """
    if fam.kind == "not_an_account":        # a kind, not the state of the same name
        return False
    if fam.id == "vault":
        return bool(_vault_names(ctx))
    if fam.kind == "folder":
        return bool(_notes_folder(ctx))
    if fam.kind in ("card", "cli"):
        # Contract section 5: every store entry saved, OR an environment
        # variable set. The environment is checked first because it wins on
        # every read and costs nothing to ask.
        if any(_env_set(name) for name in fam.env_names):
            return True
        return bool(fam.store_entries) and all(
            _store_has(entry) for entry in fam.store_entries)
    if any(_settings_value(key) for key in fam.address_keys):
        return True
    if any(_store_has(entry) for entry in fam.store_entries):
        return True
    return any(_env_set(name) for name in fam.env_names)


def _env_wins(fam: Family) -> list:
    """The environment variable NAMES that are set and win over the saved value.

    For the three card services this is the same fact
    jarvis_connect_account._winning_source reports ("environment" exactly when
    the variable is set), asked here through the same variables. For a
    settings family an address's variable wins over accounts.json the same way
    (jarvis_accounts.env_set/value above), so those names are added too. Names
    only, never a value.
    """
    names = [name for name in fam.env_names if _env_set(name)]
    if fam.kind in ("settings", "folder"):
        for key in fam.address_keys:
            name = ENV.get(key, "")
            if name and _env_set(name) and name not in names:
                names.append(name)
    return names


def _context(probe: bool, only: str = "") -> dict:
    """One call's shared reading, so a whole list is answered consistently.

    With `probe=False` this is an empty box: nothing is imported, no verifier
    runs, no socket opens. With `probe=True` the owning module's own verifier
    runs ONCE - jarvis_connect_account for the three card services and
    jarvis_google_calendar for the OAuth way - never a request built here
    (contract section 8). `only` narrows that to the ONE family being asked
    about, so "test my Google Calendar" cannot also dial GitHub.
    """
    ctx = {"connect": {}, "google": None, "ran_at": None, "vault": None, "notes": None}
    if not probe:
        return ctx
    wants_connect = (not only) or only.startswith("connect_account:")
    wants_google = (not only) or only == "google"
    connect = _backend("jarvis_connect_account") if wants_connect else None
    if connect is not None:
        try:
            for row in connect.status(probe=True) or []:
                if isinstance(row, dict) and row.get("service"):
                    ctx["connect"][str(row["service"])] = row
            ctx["ran_at"] = time.time()
        except Exception:                   # noqa: BLE001 - no verifier, no "connected"
            ctx["connect"] = {}
    google = _backend("jarvis_google_calendar") if wants_google else None
    if google is not None:
        try:
            seen = google.status()
            if isinstance(seen, dict):
                ctx["google"] = seen
                ctx["ran_at"] = time.time()
        except Exception:                   # noqa: BLE001 - same rule for Google
            ctx["google"] = None
    return ctx


def _verified(fam: Family, ctx: dict) -> tuple:
    """(did the verifier pass, did a verifier RUN) for this family in this call.

    The two are deliberately separate: a family whose verifier never ran is
    never "connected", and `tested` is True only when one actually ran.
    """
    if fam.verify.startswith("connect_account:"):
        service_id = fam.verify.split(":", 1)[1]
        row = (ctx.get("connect") or {}).get(service_id)
        if not isinstance(row, dict):
            return False, False
        return bool(row.get("connected")), bool(row.get("configured"))
    if fam.verify == "google":
        seen = ctx.get("google")
        if not isinstance(seen, dict):
            return False, False
        return bool(seen.get("connected")), True
    return False, False


def _entry_names(fam: Family, ctx: dict) -> list:
    """The entry NAMES this family is known by - never a value."""
    if fam.id == "vault":
        return _vault_names(ctx)
    return list(fam.store_entries)


def _full(sentence: str) -> str:
    """One table sentence, made safe to join after another (some have no full
    stop of their own - "Say \"connect my GitHub\"" - and a run-on would read
    as one instruction instead of two)."""
    text = str(sentence or "").strip()
    if text and text[-1] not in ".!?":
        return text + "."
    return text


# --------------------------------------------------------------------------
#   The public answers (contract section 2, in its order)
# --------------------------------------------------------------------------

def account_from_words(text: object) -> Optional[str]:
    """The family a person's words name, or None when no family does.

    Whole-word matching against the closed vocabulary in FAMILIES, earliest
    match first and the longest phrase at that place, exactly like
    jarvis_connect_account.service_from_words - so "google calendar" lands on
    Google Calendar rather than the iCal link, "google drive" on the family
    that is not an account at all, and "disconnect notion" on Notion. A
    sentence naming nothing on the list returns None, which is what makes the
    answer honest instead of a row about something else.
    """
    try:
        words = " ".join(str(text or "").lower().split())
    except Exception:                       # noqa: BLE001 - an unprintable object
        return None
    if not words:
        return None
    best = None
    for fam in FAMILIES:
        for phrase in fam.words:
            found = re.search(r"\b" + re.escape(phrase) + r"s?\b", words)
            if found is None:
                continue
            at = found.start()
            if best is None or at < best[0] or (at == best[0] and len(phrase) > best[1]):
                best = (at, len(phrase), fam.id)
    return best[2] if best else None


def state_of(account_id: str, *, probe: bool = False) -> dict:
    """One family's row: state, abilities, change, remove, and the honest limits.

    `{}` for a name that is not a family (the same "no such row" answer as an
    empty list, never an exception and never an echoed name).

    `probe=False` (the default, and the only mode /api/accounts uses) opens no
    socket and writes nothing; a verifier only runs with `probe=True`.
    """
    fam = _family(account_id)
    if fam is None:
        return {}
    wants = bool(probe) and fam.verify != "none"
    return _row(fam, wants, _context(wants, fam.verify if wants else ""))


def abilities(account_id: str) -> list:
    """One row per action this family's abilities list names, resolved LIVE.

    `tier` comes from jarvis_framework.action_tier - the one authority - and
    `why`/`classified` from jarvis_gate.risk_for. Nothing here is a copy of
    either table, and nothing here falls back to a guess: if the permission
    table cannot be read on this PC, `tier` is None, `says` is "" and `asks` is
    None, so no card is ever promised a permission it does not have and the
    word "never" is never invented.
    """
    fam = _family(account_id)
    if fam is None:
        return []
    framework = _backend("jarvis_framework")
    asks_first = _backend("jarvis_asks_first")
    gate = _backend("jarvis_gate")
    says_table = {}
    if asks_first is not None:
        try:
            says_table = dict(asks_first.SAYS)
        except Exception:                   # noqa: BLE001 - no table, no words
            says_table = {}
    out = []
    for action in fam.abilities:
        tier = None
        if framework is not None:
            try:
                got = str(framework.action_tier(action) or "")
            except Exception:               # noqa: BLE001 - unreadable table
                got = ""
            if got in _TIERS:
                tier = got
        says = str(says_table.get(tier, "")) if tier is not None else ""
        asks = (tier in ("ask", "never")) if tier is not None else None
        why, classified = "", False
        if gate is not None:
            try:
                risk = gate.risk_for(action)
                why = str(risk.get("why", "") or "")
                classified = bool(risk.get("classified"))
            except Exception:               # noqa: BLE001 - unreadable gate table
                why, classified = "", False
            if not why and not classified:
                why = _GATE_UNREADABLE
        else:
            why = _GATE_UNREADABLE
        if tier is None:
            # The permission table is the authority; without it the row says
            # so rather than borrowing a tier from somewhere else.
            why = _PERMISSION_UNREADABLE
        out.append({"action": action, "words": fam.can, "tier": tier, "says": says,
                    "asks": asks, "why": why, "classified": classified})
    return out


def state_words(account_id: str, *, probe: bool = False) -> str:
    """ONE family, in plain words: is it connected, what can it do, what can be
    changed, how is it disconnected, and what is the honest caveat.

    `probe=False` says "not tested just now" and never "connected" (contract
    section 5). An unknown name gets a plain sentence that does not echo it.
    """
    fam = _family(account_id)
    if fam is None:
        return "There is no account by that name in the list on this PC."
    wants = bool(probe) and fam.verify != "none"
    row = _row(fam, wants, _context(wants, fam.verify if wants else ""))
    parts = [f"{fam.name}: {_STATE_WORDS[row['state']]}."]
    if row["state"] == _STATE_NOT_AN_ACCOUNT:
        parts.append(_full(fam.can))
        parts.append(_full(fam.change))
        parts.append(_full(fam.remove))
        if fam.limit:
            parts.append(_full(fam.limit))
        return " ".join(part for part in parts if part)
    if row["abilities"]:
        said = []
        for ability in row["abilities"]:
            action = str(ability["action"]).replace("_", " ")
            if ability["tier"] is None:
                said.append(action + " (not known on this PC)")
            else:
                words = str(ability["says"] or ability["tier"]).rstrip(".")
                said.append(action + " - " + words)
        parts.append("Jarvis can: " + "; ".join(said) + ".")
    parts.append(_full(fam.can))
    parts.append(_full(fam.change))
    parts.append(_full(fam.remove))
    if fam.limit:
        parts.append(_full(fam.limit))
    return " ".join(part for part in parts if part)


def sentence(*, probe: bool = False) -> str:
    """The whole chat answer: every family, its state, and the five facts.

    One line per family - what it is, whether it is connected, what Jarvis can
    do with it, where it is changed and how it is disconnected - so a family
    added to FAMILIES without wording is visible here at once. `probe=False`
    is the default, and it opens no connection.
    """
    ctx = _context(bool(probe))
    lines = [_TITLE + ":"]
    for fam in FAMILIES:
        row = _row(fam, bool(probe), ctx)
        state = _STATE_WORDS[row["state"]]
        if row["state"] == _STATE_NOT_AN_ACCOUNT:
            lines.append(f"- {fam.name}: {state}. {_full(fam.can)} {_full(fam.change)} "
                         f"{_full(fam.remove)}")
            continue
        line = (f"- {fam.name}: {state}. {_full(fam.can)} Change: {_full(fam.change)} "
                f"Disconnect: {_full(fam.remove)}")
        if fam.limit:
            line += f" Note: {_full(fam.limit)}"
        lines.append(line)
    if probe:
        tail = ("Each account with a test was checked just now; \"connected\" means that "
                "test passed on this PC.")
    else:
        tail = ("Nothing above was tested just now - opening this list opens no "
                "connection on this PC. Ask about one by name (\"is my calendar "
                "connected?\") for a real test, or say \"connect my GitHub\" to add one.")
    return "\n".join(lines + ["", tail])


def rows(*, probe: bool = False) -> list:
    """One row per family, in FAMILIES' order (contract section 5's shape)."""
    ctx = _context(bool(probe))
    return [_row(fam, bool(probe), ctx) for fam in FAMILIES]


def accounts_overview(*, probe: bool = False) -> list:
    """The same list, under the name /api/self composes (contract section 7.2).

    An alias on purpose, not a second builder: two builders would drift.
    """
    return rows(probe=probe)


def accounts_view(*, probe: bool = False) -> dict:
    """What GET /api/accounts answers (contract section 2).

    Exactly the five keys the contract names. `probed` says whether this call
    was allowed to test anything at all; `checked_at` is the time the verifiers
    actually ran, and None when none did - never a made-up time, the same rule
    as `connected_at`. The addresses answer keeps its own `view()` above; the
    two are deliberately separate functions with separate shapes.
    """
    ctx = _context(bool(probe))
    families = [_row(fam, bool(probe), ctx) for fam in FAMILIES]
    return {
        "available": True,
        "title": _TITLE,
        "probed": bool(probe),
        "families": families,
        "checked_at": ctx.get("ran_at") if probe else None,
    }


def handle_accounts_get(query: str = "") -> tuple:
    """GET /api/accounts's answer: always (200, accounts_view(probe=False)).

    The query string is IGNORED, deliberately: `probe` must never be reachable
    over HTTP in this change (contract section 6), so there is no request shape
    that can make this open a socket.
    """
    return 200, accounts_view(probe=False)


def _row(fam: Family, probe: bool, ctx: dict) -> dict:
    """One family's row. Every value here is a NAME, a word or a boolean."""
    entries = _entry_names(fam, ctx)
    configured = _configured(fam, ctx)
    tested = False
    if fam.kind == "not_an_account":        # a kind, not the state of the same name
        state = _STATE_NOT_AN_ACCOUNT
    else:
        state = _STATE_SAVED if configured else _STATE_NOT_SET_UP
        if probe and fam.verify != "none":
            passed, ran = _verified(fam, ctx)
            tested = bool(ran)
            if ran:
                state = _STATE_CONNECTED if passed else (
                    _STATE_SAVED if configured else _STATE_NOT_SET_UP)
    return {
        "id": fam.id,
        "name": fam.name,
        "kind": fam.kind,
        # "named": this family's credential entries are known by name in this
        # answer (a fixed store entry, or a vault name the owner saved).
        "named": bool(entries),
        "state": state,
        "tested": tested,
        "store_entries": entries,
        "env_wins": _env_wins(fam),
        "change": fam.change,
        "remove": fam.remove,
        # Contract section 5 names a "connect" field but the frozen Family
        # dataclass has none, and in this table every family has exactly one
        # door, so the "where a change is made" sentence IS the "how to
        # connect a new one" sentence. Reported rather than invented twice.
        "connect": fam.change,
        "limit": fam.limit,
        "can": fam.can,
        "abilities": abilities(fam.id),
        # Credential Manager keeps no timestamp, so this is the honest answer
        # and never a made-up date (contract section 5).
        "connected_at": None,
        "connected_at_known": False,
    }
