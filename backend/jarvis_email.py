"""jarvis_email.py - lets Jarvis read the owner's own inbox. Nothing else.

WHAT IT IS FOR
The third of the four integrations docs/ANDROID-FEATURE-AUDIT.md named
("Calendar (CalDAV), notes (Obsidian/Joplin local REST), home (Home
Assistant's MCP server) - read-only first, no cloud keys"), plus this one:
IMAP, the open protocol nearly every mail provider still speaks for reading
mail with a plain username and password - no Google/Microsoft OAuth
registration, no cloud key. Same shape and same reasoning as
`jarvis_calendar.py`, written right after it and deliberately kept as close
to its structure as an entirely different protocol allows.

READ-ONLY, ON PURPOSE, WITH NO GROWTH PATH LEFT HALF-BUILT
IMAP itself can mark messages read, move them, or delete them. None of that
is here. This module has exactly one job - list recent messages and preview
them - and no function that changes anything on the server. Sending mail
(SMTP) is a different protocol entirely and is not implemented, imported, or
mentioned again below; a "reply" or "send" capability is a materially
different, higher-consequence action (`jarvis_browser_control.py`'s own
docstring makes the same point about a browser step: it "almost always sends
something to whoever is on the other end") and would need its own plan,
its own card, and its own explicit decision to build - not a quiet extension
of a tool whose whole pitch was "read-only".

THE PERMISSION MODEL, WHICH IS THE POINT
    plan(limit, unread_only)   Works out the ONE connection this would make -
                                host, mailbox, search criterion, how many
                                messages - against configured credentials.
                                Opens no socket. Returns a Plan.
    run(plan, approved)        Connects once, searches, fetches headers and a
                                short preview for up to `limit` messages, and
                                disconnects. Never touches message flags.

Same split, same reason, as `jarvis_calendar.py`'s own docstring: reading
the owner's own account is still a request leaving this machine, and this
module does not decide on its own that it may be sent. See
backend/README.md's `email-wiring` section for the exact `jarvis_gate`/
`jarvis-framework.toml` lines and the tier this ships with, and
`jarvis_calendar.py`'s docstring for why a pure read defaults to `auto`
rather than `ask` - the same reasoning applies here unchanged.

CREDENTIALS - NEVER STORED HERE, NEVER LOGGED, NEVER ON A CARD
`JARVIS_IMAP_HOST`, `JARVIS_IMAP_PORT`, `JARVIS_IMAP_USER`,
`JARVIS_IMAP_PASSWORD`, `JARVIS_IMAP_MAILBOX` are read fresh from the
environment on every call, exactly like `jarvis_calendar.py`'s three. This
module never writes them to disk and never puts the password in a `Plan` or
`describe()`'s output.

WHAT A "PREVIEW" ACTUALLY SHOWS, AND WHY IT IS SHORT
The full body of an email can be arbitrarily large and can carry attachments,
tracking pixels, and HTML nobody asked Jarvis to render. `_preview` takes
only the first text/plain part, strips it to plain characters, and caps it
at `_MAX_PREVIEW_CHARS` - short enough to say "here is roughly what this
is about", never long enough to be the whole message. Providers text the
model reads should say what a message needs, not reproduce it.

TESTING WITHOUT A REAL IMAP SERVER
`run()` takes an injectable `fetch_messages`, exactly the same shape as
`jarvis_calendar.run()`'s `fetch` - it returns a list of raw RFC 822 byte
strings, and the actual protocol conversation (`imaplib`, stdlib, no new
dependency) lives only in `_default_fetch_messages`, which nothing in this
file calls except itself.
"""

from __future__ import annotations

import email
import os
import re
from dataclasses import dataclass, asdict
from email.header import decode_header
from typing import Callable, Optional

HOST_ENV = "JARVIS_IMAP_HOST"
PORT_ENV = "JARVIS_IMAP_PORT"
USER_ENV = "JARVIS_IMAP_USER"
PASSWORD_ENV = "JARVIS_IMAP_PASSWORD"
MAILBOX_ENV = "JARVIS_IMAP_MAILBOX"

_DEFAULT_PORT = 993
_DEFAULT_MAILBOX = "INBOX"

_MAX_MESSAGES = 25
_MAX_HEADER_CHARS = 300
_MAX_PREVIEW_CHARS = 400


def _configured() -> bool:
    return bool(os.environ.get(HOST_ENV, "").strip())


def authenticated() -> bool:
    """Whether a username is configured. Never reveals the password."""
    return bool(os.environ.get(USER_ENV, "").strip())


# --------------------------------------------------------------------------
#   The plan - one connection, worked out locally, opened by no one yet
# --------------------------------------------------------------------------

@dataclass
class Plan:
    host: str
    port: int
    mailbox: str
    criterion: str          # "UNSEEN" or "ALL" - IMAP SEARCH keyword, verbatim
    limit: int
    if_refused: str = ""
    authenticated: bool = False
    reason_empty: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.host)

    def as_dict(self) -> dict:
        return asdict(self)


def plan(limit: int = 10, *, unread_only: bool = True) -> Plan:
    """Work out the one connection this would make. Opens no socket."""
    limit = max(1, min(_MAX_MESSAGES, int(limit)))
    host = os.environ.get(HOST_ENV, "").strip()
    mailbox = os.environ.get(MAILBOX_ENV, "").strip() or _DEFAULT_MAILBOX
    try:
        port = int(os.environ.get(PORT_ENV, "") or _DEFAULT_PORT)
    except ValueError:
        port = _DEFAULT_PORT
    criterion = "UNSEEN" if unread_only else "ALL"

    if not host:
        return Plan(
            host="", port=port, mailbox=mailbox, criterion=criterion, limit=limit,
            if_refused="nothing is read; the inbox stays unknown to Jarvis",
            authenticated=authenticated(),
            reason_empty=f"{HOST_ENV} is not set - there is no mail server to read")
    return Plan(
        host=host, port=port, mailbox=mailbox, criterion=criterion, limit=limit,
        if_refused="nothing is read; the inbox stays unknown to Jarvis",
        authenticated=authenticated())


def describe(p: Plan) -> str:
    """The card text. The literal connection parameters - never a summary."""
    if not p.configured:
        return (f"Jarvis would like to check the mailbox \"{p.mailbox}\" for "
                f"{'unread mail' if p.criterion == 'UNSEEN' else 'mail'}, but "
                f"{p.reason_empty}. Nothing would be sent.")
    auth_line = (
        "Authenticated: this will log in to that server with the configured "
        "IMAP username and password."
        if p.authenticated else
        "No credentials are configured - this connection will very likely be "
        "refused by the server, which requires them for nearly every real "
        "IMAP account."
    )
    which = "unread messages only" if p.criterion == "UNSEEN" else "all messages"
    lines = [
        f"Jarvis would like to read up to {p.limit} {which} from the "
        f"\"{p.mailbox}\" mailbox on {p.host}:{p.port}.",
        "",
        f"1 connection, to {p.host}:{p.port}, mailbox \"{p.mailbox}\", "
        f"search {p.criterion}, limit {p.limit}.",
        auth_line,
        "",
        "For each message: sender, subject, date, and a short plain-text "
        f"preview capped at {_MAX_PREVIEW_CHARS} characters. Full message "
        "bodies and attachments are never read.",
        "",
        "What leaves this machine: the IMAP login handshake to that host, "
        "and nothing else. Not your other files, not your conversation.",
        "",
        f"If you say no: {p.if_refused}",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------
#   Execution - one connection, then a bounded, honest preview
# --------------------------------------------------------------------------

def _default_fetch_messages(p: Plan) -> list:
    """The real IMAP call. `imaplib` is stdlib - no new dependency. Fetches
    the `limit` most recent matches, newest first, as raw RFC 822 bytes, then
    disconnects. Credentials read fresh from the environment, never cached."""
    import imaplib

    user = os.environ.get(USER_ENV, "")
    password = os.environ.get(PASSWORD_ENV, "")
    conn = imaplib.IMAP4_SSL(p.host, p.port)
    try:
        conn.login(user, password)
        conn.select(p.mailbox, readonly=True)
        status, data = conn.search(None, p.criterion)
        if status != "OK":
            raise RuntimeError(f"SEARCH failed: {status}")
        ids = (data[0] or b"").split()
        ids = ids[-p.limit:][::-1]  # newest first
        raw_messages = []
        for msg_id in ids:
            status, msg_data = conn.fetch(msg_id, "(RFC822)")
            if status != "OK" or not msg_data or not msg_data[0]:
                continue
            raw_messages.append(msg_data[0][1])
        return raw_messages
    finally:
        try:
            conn.close()
        except Exception:
            pass
        try:
            conn.logout()
        except Exception:
            pass


def _decode(value: Optional[str]) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    out = []
    for text, enc in parts:
        if isinstance(text, bytes):
            out.append(text.decode(enc or "utf-8", errors="replace"))
        else:
            out.append(text)
    return "".join(out)


def _preview(msg: "email.message.Message") -> str:
    """The first text/plain part, stripped and capped. HTML-only messages
    get no preview rather than raw markup - showing tags is worse than
    showing nothing, and rendering HTML is not this module's job."""
    part = None
    if msg.is_multipart():
        for candidate in msg.walk():
            if candidate.get_content_type() == "text/plain":
                part = candidate
                break
    elif msg.get_content_type() == "text/plain":
        part = msg
    if part is None:
        return ""
    try:
        raw = part.get_payload(decode=True) or b""
        charset = part.get_content_charset() or "utf-8"
        text = raw.decode(charset, errors="replace")
    except Exception:
        return ""
    text = re.sub(r"\s+", " ", text).strip()
    return text[:_MAX_PREVIEW_CHARS]


def _parse_message(raw: bytes) -> dict:
    msg = email.message_from_bytes(raw)
    return {
        "from": _decode(msg.get("From"))[:_MAX_HEADER_CHARS],
        "subject": _decode(msg.get("Subject"))[:_MAX_HEADER_CHARS],
        "date": _decode(msg.get("Date"))[:_MAX_HEADER_CHARS],
        "preview": _preview(msg),
    }


def run(p: Plan, *, fetch_messages: Optional[Callable[[Plan], list]] = None,
        approved: bool = False) -> dict:
    """Execute an approved plan. `approved` has no default of True.

    `fetch_messages` is injectable so the parsing below can be proven with
    no socket, the same technique `jarvis_calendar.run()`'s `fetch` uses.
    """
    if not approved:
        return {"ok": False, "reason": "not approved; nothing was read",
                "plan": p.as_dict()}
    if not p.configured:
        return {"ok": False, "reason": p.reason_empty, "messages": []}

    getter = fetch_messages or _default_fetch_messages
    try:
        raw_messages = getter(p)
    except Exception as exc:
        return {"ok": False,
                "reason": f"the connection failed: {type(exc).__name__}: {exc}",
                "messages": []}

    messages = [_parse_message(raw) for raw in raw_messages[:p.limit]]
    return {"ok": True, "messages": messages, "mailbox": p.mailbox,
            "criterion": p.criterion}
