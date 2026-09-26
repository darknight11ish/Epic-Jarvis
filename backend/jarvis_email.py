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
(Built 2026-09-25 exactly that way, in jarvis_email_send.py; this module still sends nothing.)

THE PERMISSION MODEL, WHICH IS THE POINT
    plan(limit, unread_only)   Works out the ONE connection this would make -
                                host, mailbox, search criterion, how many
                                messages - against configured credentials.
                                Opens no socket. Returns a Plan.
    run(plan, approved)        Connects once, searches, fetches headers and a
                                short preview for up to `limit` messages, and
                                disconnects. Never touches message flags.

Two narrower reads, for the morning briefing (jarvis_briefing.py), gated
by the caller under the same action and tier:
    count(plan, approved)      How many match - the number only; no FETCH.
    senders(plan, approved)    How many match, and the From line ONLY of the
                                newest five, read with BODY.PEEK so nothing is
                                marked as read. Names only, decoded, tidied.

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

ONE-TIME CODES AND SIGN-IN LINKS ARE HIDDEN (the Muse audit, 2026-09-25).
Every subject, preview and sender name read here goes through `_hide`
(jarvis_mail_mask.py) first: "Your code is 482913" becomes "Your code is
[a one-time code, hidden]", and a password-reset or magic sign-in link
becomes "[a sign-in link, hidden]". What it cannot catch is listed in that
module. Without it, the text is withheld rather than shown as it is.

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

#: Seconds for the email-reading tool's one mail connection to answer.
_FETCH_TIMEOUT = 30.0


def _default_fetch_messages(p: Plan) -> list:
    """The real IMAP call. `imaplib` is stdlib - no new dependency. Fetches
    the `limit` most recent matches, newest first, as raw RFC 822 bytes, then
    disconnects. Credentials read fresh from the environment, never cached."""
    import imaplib

    user = os.environ.get(USER_ENV, "")
    password = os.environ.get(PASSWORD_ENV, "")
    # A timeout, like the other IMAP calls here: without one, a mail server
    # that stops answering held the chat answer for ever (2026-09-26 bug
    # audit, finding 6).
    conn = imaplib.IMAP4_SSL(p.host, p.port, timeout=_FETCH_TIMEOUT)
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
            # LookupError, separately from the decode errors `errors=
            # "replace"` already covers. `errors="replace"` handles bytes
            # that are not valid IN a codec; it does nothing at all when the
            # CODEC ITSELF does not exist, and a header naming a charset
            # Python has never heard of ("charset=unicode", a truncated
            # name, a typo from some sender's mail client) raises LookupError
            # from inside .decode(). That propagated out of _decode, out of
            # the message loop, and failed the entire mailbox read - so one
            # malformed header from one sender broke every email_check until
            # that message was deleted by hand.
            try:
                out.append(text.decode(enc or "utf-8", errors="replace"))
            except LookupError:
                out.append(text.decode("utf-8", errors="replace"))
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
    # Codes and sign-in links hidden BEFORE the cut, so a link the cut would
    # have split is still recognised; the subject tells it whether the
    # message carries a code.
    return _hide(text, _decode(msg.get("Subject")), cap=_MAX_PREVIEW_CHARS)


#: What stands in for email text when jarvis_mail_mask.py is missing.
_MASK_MISSING = "[not shown: jarvis_mail_mask.py is missing on this PC]"


def _hide(text: str, subject: str = "", *, cap: int = _MAX_HEADER_CHARS) -> str:
    """One-time codes and password-reset / sign-in links replaced by plain
    markers (jarvis_mail_mask.py; the Muse audit, 2026-09-25), then cut to
    `cap`. Every subject, preview and sender name this module reads goes
    through here, so the model, both apps, the briefing and any log only
    ever see the hidden version. Without that module the text is WITHHELD,
    never shown as it is."""
    if not text:
        return ""
    try:
        import jarvis_mail_mask as MASK
    except Exception:
        return _MASK_MISSING
    return MASK.cap(MASK.hide(text, subject=subject), cap)


def _parse_message(raw: bytes) -> dict:
    msg = email.message_from_bytes(raw)
    return {
        "from": _hide(_decode(msg.get("From"))),
        "subject": _hide(_decode(msg.get("Subject"))),
        "date": _decode(msg.get("Date"))[:_MAX_HEADER_CHARS],
        "preview": _preview(msg),
    }


#: How long the count's connection may take, in seconds. The preview's own
#: connection above sets none, which is the owner's existing behaviour and is
#: left alone here.
_COUNT_TIMEOUT = 20.0


def _default_count(p: Plan) -> int:
    """How many messages match - the NUMBER only. Logs in, opens the mailbox
    read-only, searches, and disconnects. Fetches no message: no sender, no
    subject, no body is ever read by this function."""
    import imaplib

    user = os.environ.get(USER_ENV, "")
    password = os.environ.get(PASSWORD_ENV, "")
    conn = imaplib.IMAP4_SSL(p.host, p.port, timeout=_COUNT_TIMEOUT)
    try:
        conn.login(user, password)
        conn.select(p.mailbox, readonly=True)
        status, data = conn.search(None, p.criterion)
        if status != "OK":
            raise RuntimeError(f"SEARCH failed: {status}")
        return len((data[0] or b"").split())
    finally:
        try:
            conn.close()
        except Exception:
            pass
        try:
            conn.logout()
        except Exception:
            pass


def count(p: Plan, *, search: Optional[Callable[[Plan], int]] = None,
          approved: bool = False) -> dict:
    """How many messages match the plan's search (unread, for the morning
    briefing) - a number, and nothing about any message. The same one
    connection `describe()` shows, gated the same way by the caller;
    `approved` has no default of True. `search` is injectable, like
    `run()`'s `fetch_messages`, so this is provable with no socket.

    The reason on a failure is the exception's NAME only: its message could
    quote the server's reply."""
    if not approved:
        return {"ok": False, "reason": "not approved; nothing was read"}
    if not p.configured:
        return {"ok": False, "reason": p.reason_empty}
    getter = search or _default_count
    try:
        n = int(getter(p))
    except Exception as exc:
        return {"ok": False, "reason": f"the connection failed ({type(exc).__name__})"}
    return {"ok": True, "count": max(0, n), "mailbox": p.mailbox, "criterion": p.criterion}


# --------------------------------------------------------------------------
#   Who the newest unread messages are from - for the morning briefing
# --------------------------------------------------------------------------
#
# The owner's decision of 2026-09-25: the briefing shows how many new emails
# AND who they are from ("3 new emails, from Alex, your bank and GitHub"),
# with a setting to show the number only (jarvis_briefing.py keeps it).
#
# Still read-only, and narrower than run(): ONE connection that logs in,
# opens the mailbox read-only (EXAMINE), searches, and then asks for the
# From line ONLY of the newest few matches -
#     FETCH <id> (BODY.PEEK[HEADER.FIELDS (FROM)])
# PEEK, so the server does not set \Seen: nothing is marked as read. No
# subject, no date, no body, no attachment is asked for, and no STORE,
# COPY, MOVE or EXPUNGE is ever sent.

#: How many of the newest unread messages have their sender read.
_MAX_SENDERS = 5
#: One sender's name, at most - long enough for "Northern Rail Customer
#: Services", short enough that a hostile name cannot fill the screen.
_MAX_SENDER_CHARS = 60

#: The one FETCH item this asks for. BODY.PEEK, never BODY or RFC822: a
#: plain BODY[...] fetch sets \Seen on most servers when the mailbox is
#: selected read-write (it is not, here - both are belt and braces).
SENDER_FETCH = "(BODY.PEEK[HEADER.FIELDS (FROM)])"


def _default_senders(p: Plan, newest: int) -> tuple:
    """(how many match, [raw From header bytes of the newest `newest`,
    newest first]). ONE connection; the From line only; PEEK, read-only.
    Credentials read fresh from the environment, never cached."""
    import imaplib

    user = os.environ.get(USER_ENV, "")
    password = os.environ.get(PASSWORD_ENV, "")
    conn = imaplib.IMAP4_SSL(p.host, p.port, timeout=_COUNT_TIMEOUT)
    try:
        conn.login(user, password)
        conn.select(p.mailbox, readonly=True)
        status, data = conn.search(None, p.criterion)
        if status != "OK":
            raise RuntimeError(f"SEARCH failed: {status}")
        ids = (data[0] or b"").split()
        heads = []
        for msg_id in ids[-newest:][::-1] if newest > 0 else []:
            status, got = conn.fetch(msg_id, SENDER_FETCH)
            if status != "OK" or not got:
                continue
            for part in got:
                if isinstance(part, tuple) and len(part) > 1 and isinstance(part[1], bytes):
                    heads.append(part[1])
                    break
        return len(ids), heads
    finally:
        try:
            conn.close()
        except Exception:
            pass
        try:
            conn.logout()
        except Exception:
            pass


#: Control characters, and the invisible "format" characters a sender can
#: use to make a name read differently from what it is (right-to-left
#: overrides, zero-width joiners). Neither belongs in a name on a screen.
_INVISIBLE = ("Cc", "Cf", "Cs", "Co", "Cn")


def _tidy(text: str) -> str:
    import unicodedata
    t = "".join(" " if unicodedata.category(ch) in _INVISIBLE else ch for ch in str(text or ""))
    t = " ".join(t.split()).strip(" \"'<>")
    if len(t) > _MAX_SENDER_CHARS:
        t = t[:_MAX_SENDER_CHARS - 3].rstrip() + "..."
    return t


def sender_name(raw_header) -> str:
    """One sender, as the owner's mail app would show it: the display name
    ("Alex Smith"), decoded (RFC 2047) and tidied; with no name, the whole
    address ("noreply@github.com"). Not the part before the @ alone: that
    is "noreply", "info" or "support" as often as not, which says nothing
    about who wrote. "" when there is nothing readable."""
    from email.utils import getaddresses
    if isinstance(raw_header, bytes):
        try:
            msg = email.message_from_bytes(raw_header)
            value = msg.get("From") or ""
        except Exception:
            return ""
    else:
        value = str(raw_header or "")
    value = str(value)[:2000]
    try:
        pairs = getaddresses([value])
    except Exception:
        pairs = []
    name, addr = pairs[0] if pairs else ("", "")
    shown = _tidy(_decode(name)) if name else ""
    if not shown:
        shown = _tidy(_decode(addr)) if addr else ""
    if not shown and not pairs:
        shown = _tidy(_decode(value))
    return _hide(shown, cap=_MAX_SENDER_CHARS)


def senders(p: Plan, *, fetch: Optional[Callable[[Plan, int], tuple]] = None,
            approved: bool = False, newest: int = _MAX_SENDERS) -> dict:
    """How many messages match (unread, for the morning briefing), and who
    the newest `newest` (at most 5) are from - names only, each once, newest
    first. ONE connection, the From line only, nothing marked as read.
    `approved` has no default of True; the caller gates it (the same action
    and tier as count()). `fetch` is injectable, like run()'s.

    {"ok", "count", "senders": [str], "looked_at": int} - `looked_at` is how
    many messages had their From line read, so a caller can say "the newest
    5" when there are more. A failure's reason is the exception's NAME only:
    its message could quote the server's reply."""
    if not approved:
        return {"ok": False, "reason": "not approved; nothing was read"}
    if not p.configured:
        return {"ok": False, "reason": p.reason_empty}
    newest = max(0, min(_MAX_SENDERS, int(newest)))
    getter = fetch or _default_senders
    try:
        n, heads = getter(p, newest)
        n = max(0, int(n))
        heads = list(heads or [])[:newest]
    except Exception as exc:
        return {"ok": False, "reason": f"the connection failed ({type(exc).__name__})"}
    names, seen = [], set()
    for h in heads:
        name = sender_name(h)
        key = name.casefold()
        if name and key not in seen:
            seen.add(key)
            names.append(name)
    return {"ok": True, "count": n, "senders": names, "looked_at": min(len(heads), n),
            "mailbox": p.mailbox, "criterion": p.criterion}


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
