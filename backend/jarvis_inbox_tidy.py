"""jarvis_inbox_tidy.py - "Inbox tidy by voice": archive, star, mark as read, or
move to Trash a checked list of emails, after ONE approval card that lists
every one of them, with 10 minutes to Undo.

NEW MODULE, shipped whole. inbox-tidy.patch installs its two routes
(docs/JARVIS-API.md section 95) and gives the gate its words; jarvis_agent.py
calls plan(), describe() and run() for the model's `tidy_inbox` tool.

THE OWNER'S DECISION (2026-09-28, CLAUDE.md)
"Inbox tidy by voice: yes - archive, star, mark read, or move to Trash. One
approval card lists every email it will touch, approved on screen (never by
voice), then Undo. "Delete" only ever moves to Trash. The card says when the
choice came from reading email (outside text). A new named way out of the PC
(ARCHITECTURE section 4) and its own gate action, like sending email." The
owner's queue answer: Undo lasts 10 minutes.

THE SAME SHAPE AS jarvis_email_send.py AND jarvis_forget_range.py
    plan(action, sender=, subject=, words=, ...)
                        Finds the emails the owner's plain words describe and
                        works out exactly what would be done to each. This
                        one READS: the card has to list every email, so it
                        connects once, opens the mailbox READ-ONLY (EXAMINE),
                        searches, and reads each match's From, Subject, Date
                        and Message-ID lines with BODY.PEEK - never a body,
                        never a flag changed. Returns a Plan (never the
                        password) - or one with a `problem`, which is never
                        asked about.
    describe(plan)      The card text: what will happen, the account, and
                        EVERY email (sender, subject, date), numbered, no
                        "and 37 more".
    run(plan, approved) Does exactly that plan, once. `approved` has no
                        default of True. A plan whose content changed after
                        it was made (its fingerprint), or whose mailbox has
                        been rebuilt since (UIDVALIDITY), or whose account
                        changed, is refused: nothing is touched.
    undo()              Puts back exactly what run() changed.

Which PERSON approves is the caller's business: jarvis_agent.py puts every
tidy_inbox call to jarvis_gate under ACTION (tier "ask" only) and runs it only
when the verdict records a person saying yes (NEEDS_A_PERSON). A spoken "yes"
approves nothing - there is no approving by voice anywhere in Jarvis.

THE FOUR ACTIONS, AND THE ONE THAT IS NOT THERE
    archive     out of the inbox into the account's Archive folder (Gmail:
                the Inbox label comes off; the mail stays in All Mail).
    star        the \\Flagged flag on. Only emails not already starred are
                listed, so the list is exactly what changes.
    mark_read   the \\Seen flag on. Only unread emails are listed.
    trash       into the account's Trash folder. "Delete" only ever means this.

There is NO permanent delete in this module, by construction and not only by
a check (test_inbox_tidy.py reads the source and the IMAP commands):
  * plain EXPUNGE is never sent, and CLOSE is never sent on a mailbox opened
    for changes (CLOSE silently expunges every \\Deleted message in it,
    including ones the owner or another program had marked);
  * the only \\Deleted this module ever sets is inside `_move_by_copy`, on ONE
    message, AFTER the server confirmed a copy of it is in the destination
    folder, and only on a server that offers UIDPLUS, so that `UID EXPUNGE`
    removes that one message and nothing else. A server with neither MOVE nor
    UIDPLUS is refused before anything is touched;
  * Trash is emptied by the mail provider on its own schedule. Jarvis never
    empties it.
Gmail keeps its mail under labels, so archive and trash there are label
changes (X-GM-LABELS), which delete nothing either.

UNDO: ten minutes, one tap, no card
POST /api/email/tidy/undo puts back exactly what the last tidy changed, using
what was recorded at the moment it happened: for a move, where each email is
now (found by its Message-ID in the folder it was moved to, or the server's
own COPYUID answer) and where it came from; for a flag, only the emails
whose flag Jarvis itself changed. An email the owner already moved or
deleted meanwhile is not touched and the answer says how many. The record is
IN MEMORY ONLY - never written to disk, never holding a subject or a sender,
only ids - and ends after UNDO_SECONDS or when the backend stops, whichever
comes first. Up to MAX_UNDO tidies can be waiting to be undone at once; Undo
always takes the newest first, so older changes are never undone underneath
newer ones. It needs no card: it only puts back what the owner had ten
minutes ago.

THE LIMITS
  * At most MAX_EMAILS emails at once, and never more than one approval card
    can show whole (the gate keeps 4,000 characters of a card): past that,
    nothing is listed, nothing is asked, and the answer says "too many at
    once - narrow it". A card never shows less than everything it changes.
  * At least one narrowing word (a sender, a subject, words in the email,
    "newsletters", a number of days, or "unread"). "Archive everything" is
    refused - say which emails.
  * Only plain printable ASCII search words (IMAP needs a special encoding
    for the rest, and mis-encoding a search is worse than saying so).
  * Only the mailbox in JARVIS_IMAP_MAILBOX (INBOX unless set).
  * An email with no Message-ID cannot be found again after a move, so a move
    never touches one (the card says how many were left out).

SETTINGS - THE SAME ACCOUNT AS READING EMAIL, NOTHING NEW
    JARVIS_IMAP_HOST / _PORT / _MAILBOX / _USER / _PASSWORD (or Windows
    Credential Manager), read fresh on every call, never cached, never
    written to disk (jarvis_email.py). Not new: nothing extra to set up.

THE PASSWORD (CLAUDE.md rule 3), the same care as jarvis_email_send.py: read
at the moment of connecting; sent to the account's own IMAP server only,
inside the encrypted connection whose certificate is checked
(jarvis_email.tls_context); never in a Plan, a card, a result, an error or an
event (a failure is told by the exception's NAME and a sentence of ours);
never logged; never handed to a program Jarvis starts.

RULE 1. Nothing here talks to any model. The emails' subjects are on the
card, which only the owner's own apps show; the model is told counts and
words of ours ("Archived 12 emails"), never a subject or a sender.

Standard library only (imaplib through jarvis_email's own settings). Opens
nothing on import.
"""
from __future__ import annotations

import email
import hashlib
import json
import re
import threading
import time
import unicodedata
import uuid
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Callable, Optional
from urllib.parse import urlsplit

#: The account is the one jarvis_email.py reads with - one place for the names
#: and the functions that resolve the username and password.
from jarvis_email import (HOST_ENV, MAILBOX_ENV, PASSWORD_ENV, PORT_ENV, USER_ENV,
                          _decode, _hide, imap_password, imap_user, sender_name,
                          tls_context)

try:
    import jarvis_framework as fw
except Exception:  # pragma: no cover - shipped beside it on the PC
    fw = None  # type: ignore

#: The gate action every tidy is asked under. Tier "ask" in the shipped
#: jarvis-framework.toml, and it must stay "ask" (tier_problem).
ACTION = "tidy_inbox"
#: The model-facing tool name (jarvis_agent.TOOLS) - the same words.
TOOL = "tidy_inbox"
#: The gate action reading email is decided under (jarvis_agent's
#: email_check). plan() reads, so it needs this to be allowed to read.
READ_ACTION = "email_read"

ROUTE = "/api/email/tidy"
UNDO = ROUTE + "/undo"
ROUTES = (ROUTE, UNDO)

#: The most emails one card lists. Whole - never "and 37 more". The card must
#: also fit the gate's 4,000 characters (CARD_BUDGET), which is what really
#: decides; this is the ceiling.
MAX_EMAILS = 30
#: How many characters of a card's text this module lets a plan use, so that
#: the agent's own lines on top (outside text, "what shaped this request")
#: still fit under the gate's limit. json.dumps escapes each new line as two
#: characters, and describe() is measured that way.
CARD_BUDGET = 2800
#: How long Undo lasts after a tidy.
UNDO_SECONDS = 600
UNDO_MINUTES = UNDO_SECONDS // 60
#: Tidies that can wait to be undone at once. The newest is undone first.
MAX_UNDO = 5
TIMEOUT = 30.0
MAX_TEXT_CHARS = 60
MAX_DAYS = 3650
_MAX_SENDER_ON_CARD = 24
_MAX_SUBJECT_ON_CARD = 38

#: action id -> (name shown, the card's opening question, what is said after).
ACTIONS = {
    "archive": ("Archive", "Archive {these} from your inbox?", "Archived {n}."),
    "star": ("Star", "Put a star on {these}?", "Starred {n}."),
    "mark_read": ("Mark read", "Mark {these} as read?", "Marked {n} as read."),
    "trash": ("Move to Trash", "Move {these} to Trash?", "Moved {n} to Trash."),
}
#: The move actions: they need the Message-ID to be found again.
MOVES = ("archive", "trash")

WHAT_IT_DOES = {
    "archive": ("Archive moves each one out of the inbox into your Archive folder. "
                "Nothing is deleted, and you can still search for them."),
    "star": "Star puts the star (flag) on each one. Nothing else changes.",
    "mark_read": "Mark read turns each one from unread to read. Nothing else changes.",
    "trash": ("Move to Trash puts each one in your Trash folder. Nothing is deleted "
              "for good, and Jarvis never empties Trash - your mail provider does, "
              "on its own schedule."),
}

IF_REFUSED = "nothing changes, and Jarvis tells you it did nothing."

_COMMON_TRASH = ("Trash", "Deleted Items", "Deleted Messages", "INBOX.Trash")
_COMMON_ARCHIVE = ("Archive", "Archives", "INBOX.Archive")

# --------------------------------------------------------------------------
#   The words both apps show (tools/gen_inbox_tidy_cases.py writes them into
#   the contract file each app's tests read)
# --------------------------------------------------------------------------

WORDS = {
    "title": "Inbox tidy",
    "undo": "Undo",
    "undo_left": "{minutes} min left to undo",
    "undone": "Put back. Everything is as it was before.",
    "stale": ("The connection to Jarvis is catching up, so nothing can be sent until it "
              "does."),
    "locked": "Unlock Jarvis to undo this.",
    "missing": ("Your PC's Jarvis cannot tidy your inbox yet - run apply-patches.ps1 on "
                "the PC."),
    "hidden": "Your inbox was tidied. You can undo it for a few minutes.",
}

MISSING = WORDS["missing"]

# --------------------------------------------------------------------------
#   Replaceable pieces, so the tests open nothing real
# --------------------------------------------------------------------------


def _now() -> float:
    """This module's clock: Undo's ten minutes and the dates on the card."""
    return time.time()


def _audit(event: str, detail: dict) -> None:
    """Counts and outcomes only - never an address, a subject or a word of an
    email."""
    try:
        if fw is not None:
            fw.audit_log(event, detail)
    except Exception:
        pass


def _timer(seconds: float, fn: Callable[[], None]) -> None:
    t = threading.Timer(seconds, fn)
    t.daemon = True
    t.name = "jarvis-inbox-tidy-undo"
    t.start()


def _register_with_scrubber(user: str, password: str) -> None:
    """The password's value is already hidden in logs by its variable name
    (jarvis_scrub). IMAP LOGIN sends it base64-encoded too, so that form is
    registered - belt and braces, since nothing here prints either."""
    try:
        import base64

        import jarvis_scrub
    except Exception:
        return
    for f in (password, base64.b64encode(password.encode("utf-8")).decode("ascii")):
        try:
            jarvis_scrub.register_secret(f)
        except Exception:
            pass


# --------------------------------------------------------------------------
#   Settings - read fresh every call
# --------------------------------------------------------------------------

#: A mailbox name Jarvis will use: printable ASCII, no quote or backslash.
#: Anything else needs IMAP's modified UTF-7, which this does not implement.
_SAFE_NAME = re.compile(r"^[\x20-\x21\x23-\x5b\x5d-\x7e]{1,200}$")


@dataclass(frozen=True)
class Settings:
    user: str = ""
    host: str = ""
    port: int = 993
    mailbox: str = "INBOX"
    problem: str = ""           # "" when tidying is set up

    @property
    def ready(self) -> bool:
        return not self.problem


def settings() -> Settings:
    """How the mailbox would be reached, from the environment or Windows
    Credential Manager (jarvis_email.imap_user/imap_password). Never the
    password - only whether one is set. Opens nothing."""
    import os
    user = imap_user()
    has_password = bool(imap_password())
    host = os.environ.get(HOST_ENV, "").strip()
    mailbox = os.environ.get(MAILBOX_ENV, "").strip() or "INBOX"
    raw_port = os.environ.get(PORT_ENV, "").strip()
    port, port_problem = 993, ""
    if raw_port:
        try:
            port = int(raw_port)
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            port_problem = f"{PORT_ENV} is not a port number"
            port = 993

    def s(problem: str) -> Settings:
        return Settings(user, host, port, mailbox, problem)

    if not host:
        return s(f"{HOST_ENV} is not set - tidying uses the same account as reading "
                 f"email, and there is none")
    if not user:
        return s(f"{USER_ENV} is not set, and nothing is saved in Windows Credential "
                 f"Manager either - tidying uses the same account as reading email, and "
                 f"there is none")
    if not has_password:
        return s(f"{PASSWORD_ENV} is not set, and nothing is saved in Windows Credential "
                 f"Manager either, so the mail server would refuse the login")
    if port_problem:
        return s(port_problem)
    if not _SAFE_NAME.match(mailbox):
        return s(f"{MAILBOX_ENV} holds a name Jarvis cannot use safely (plain letters, "
                 f"digits and signs only, no quotes)")
    return s("")


# --------------------------------------------------------------------------
#   The plan - the emails found, and exactly what would be done to each
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Item:
    uid: int
    message_id: str
    sender: str
    subject: str
    date: str
    seen: bool = False
    flagged: bool = False


@dataclass(frozen=True)
class Plan:
    action: str
    user: str
    host: str
    port: int
    mailbox: str
    uidvalidity: int
    asked: str                      # the owner's words as our criteria, plain
    items: tuple = ()
    left_out: int = 0               # matched, but no Message-ID (moves only)
    matched: int = 0
    problem: str = ""
    digest: str = field(default="", compare=False)

    @property
    def ready(self) -> bool:
        return not self.problem

    def as_dict(self) -> dict:
        """What may be shown or logged: counts, never a subject or sender."""
        return {"action": self.action, "count": len(self.items), "left_out": self.left_out,
                "mailbox": self.mailbox, "problem": self.problem}


def fingerprint(p: Plan) -> str:
    """A fingerprint of everything that would be changed and where. Taken
    when the plan is made; run() takes it again and touches nothing if it
    differs."""
    body = {
        "action": p.action, "user": p.user, "host": p.host, "port": p.port,
        "mailbox": p.mailbox, "uidvalidity": p.uidvalidity,
        "items": [[i.uid, i.message_id, i.sender, i.subject, i.date, i.seen, i.flagged]
                  for i in p.items],
    }
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode("utf-8")).hexdigest()


_INVISIBLE = ("Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp")


def _clean(text, cap: int) -> str:
    """One line of an email's own words, safe to put on a card: control and
    invisible characters (a right-to-left override, a line break that could
    fake a new line on the card) become spaces, runs of spaces collapse, and
    the result is cut to `cap`."""
    t = "".join(" " if unicodedata.category(ch) in _INVISIBLE else ch
                for ch in str(text or ""))
    return _cut(" ".join(t.split()), cap)


def _cut(t: str, cap: int) -> str:
    """`t` cut to `cap` characters with "...", never leaving half of a hidden-
    code marker ("[a one-time co") behind (jarvis_mail_mask.cap)."""
    if len(t) <= cap:
        return t
    try:
        import jarvis_mail_mask as MASK
        short = MASK.cap(t, cap - 3)
    except Exception:
        short = t[:cap - 3]
    return short.rstrip() + "..."


_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov",
           "Dec")


def _imap_date(d: date) -> str:
    """dd-Mon-yyyy with English month names whatever the PC's language."""
    return f"{d.day:02d}-{_MONTHS[d.month - 1]}-{d.year}"


def _shown_date(raw: str, today: date) -> str:
    try:
        d = parsedate_to_datetime(raw).date()
    except Exception:
        return "no date"
    return f"{d.day} {_MONTHS[d.month - 1]}" + (f" {d.year}" if d.year != today.year else "")


#: A Message-ID Jarvis will search for: printable ASCII, no space, quote or
#: backslash, in <angle brackets>.
_MSGID = re.compile(r"^<[\x21\x23-\x5b\x5d-\x7e]{1,240}>$")


def _q(name: str) -> str:
    """A mailbox name or search word as an IMAP quoted string. Only names
    that passed _SAFE_NAME reach here, so nothing needs escaping."""
    return '"' + name + '"'


def _plain_word(value, label: str) -> tuple:
    """(text, problem) for a search word from the model."""
    if value in (None, ""):
        return "", ""
    if not isinstance(value, str):
        return "", f"{label} must be text"
    v = " ".join(value.split())
    if not v:
        return "", ""
    if len(v) > MAX_TEXT_CHARS:
        return "", f"{label} is too long (at most {MAX_TEXT_CHARS} characters)"
    if not re.match(r"^[\x20\x21\x23-\x5b\x5d-\x7e]+$", v):
        return "", (f"{label} has a character Jarvis cannot search for safely - use plain "
                    f"letters, digits and common signs (no quotes or accents), or a part "
                    f"of the address instead")
    return v, ""


def _days(value, label: str) -> tuple:
    """(days or None, problem)."""
    if value in (None, "", False):
        return None, ""
    if isinstance(value, bool):
        return None, f"{label} must be a number of days"
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None, f"{label} must be a number of days"
    if not 1 <= n <= MAX_DAYS:
        return None, f"{label} must be between 1 and {MAX_DAYS} days"
    return n, ""


def _connect(st: Settings):
    """The real connection: encrypted, the certificate checked, logged in.
    Credentials read fresh, never cached."""
    import imaplib
    conn = imaplib.IMAP4_SSL(st.host, st.port, timeout=TIMEOUT,
                             ssl_context=tls_context(st.host))
    try:
        conn.login(st.user, imap_password())
    except imaplib.IMAP4.error:
        # A refused login. The server's own words can quote the login, so
        # they are never used: a sentence of ours instead.
        _logout(conn)
        raise _Refused("the mail server refused the login. For Gmail, check the app "
                       "password in JARVIS_IMAP_PASSWORD") from None
    except Exception:
        _logout(conn)
        raise
    return conn


def _logout(conn) -> None:
    """Ends the session WITHOUT CLOSE: CLOSE on a mailbox opened for changes
    permanently removes every message marked \\Deleted in it."""
    try:
        conn.logout()
    except Exception:
        pass


def _text(part) -> str:
    return part.decode("utf-8", "replace") if isinstance(part, bytes) else str(part or "")


def _uidvalidity(conn) -> int:
    try:
        _typ, dat = conn.response("UIDVALIDITY")
        return int(_text((dat or [b"0"])[-1]).strip() or 0)
    except Exception:
        return 0


def _caps(conn) -> set:
    try:
        typ, dat = conn.capability()
        if typ == "OK" and dat:
            return {w.upper() for w in _text(dat[0]).split()}
    except Exception:
        pass
    return set()


_FLAGS = re.compile(r"FLAGS \(([^)]*)\)", re.I)


def _fetch_head(conn, uid: int, fields: str) -> Optional[tuple]:
    """(flags as a lower-case set, the header text) of one message, or None
    when it is not there. PEEK: nothing is marked as read."""
    typ, dat = conn.uid("FETCH", str(uid), f"(FLAGS BODY.PEEK[HEADER.FIELDS ({fields})])")
    if typ != "OK" or not dat:
        return None
    head, flags = None, set()
    for part in dat:
        if isinstance(part, tuple) and len(part) > 1:
            if head is None and isinstance(part[1], (bytes, bytearray)):
                head = bytes(part[1])
            m = _FLAGS.search(_text(part[0]))
            if m:
                flags |= {f.lower() for f in m.group(1).split()}
        elif isinstance(part, (bytes, bytearray)):
            m = _FLAGS.search(_text(part))
            if m:
                flags |= {f.lower() for f in m.group(1).split()}
    if head is None:
        return None
    return flags, head.decode("utf-8", "replace")


def _msgid_of(head_text: str) -> str:
    try:
        mid = " ".join((email.message_from_string(head_text).get("Message-ID") or "").split())
    except Exception:
        return ""
    return mid if _MSGID.match(mid) else ""


def plan(action, *, sender="", subject="", words="", newsletters=False, since_days=None,
         older_than_days=None, unread_only=False, connect: Optional[Callable] = None,
         now: Optional[float] = None) -> Plan:
    """Find the emails the owner's words describe and work out what would be
    done to each. READS the mailbox (read-only, PEEK) - the card has to list
    every email - and changes nothing. A plan with a `problem` is never sent
    to a card: the problem says why, in plain words."""
    st = settings()
    now_ts = _now() if now is None else now
    today = date.fromtimestamp(now_ts)

    def refused(problem: str, **kw) -> Plan:
        p = Plan(action=str(action) if isinstance(action, str) else "", user=st.user,
                 host=st.host, port=st.port, mailbox=st.mailbox, uidvalidity=0, asked="",
                 problem=problem, **kw)
        return replace(p, digest=fingerprint(p))

    if action not in ACTIONS:
        return refused("the action must be one of: archive, star, mark_read, trash. "
                       "(There is no permanent delete: \"delete\" means trash.)")
    if st.problem:
        return refused(f"tidying the inbox is not set up on this PC: {st.problem}")
    full = _undo_full_words(now_ts)
    if full:
        return refused(full)
    s_word, why = _plain_word(sender, "the sender")
    if why:
        return refused(why)
    subj, why = _plain_word(subject, "the subject words")
    if why:
        return refused(why)
    body, why = _plain_word(words, "the search words")
    if why:
        return refused(why)
    since, why = _days(since_days, "since_days")
    if why:
        return refused(why)
    older, why = _days(older_than_days, "older_than_days")
    if why:
        return refused(why)
    if not (s_word or subj or body or newsletters is True or since or older
            or unread_only is True):
        return refused("that does not say which emails - a sender, a subject, words in the "
                       "email, newsletters, a number of days or unread. Jarvis will not "
                       "tidy \"everything\"; ask the owner which emails they mean")

    crit = ["UNDELETED"]
    said = []
    if action == "mark_read":
        crit.append("UNSEEN")
    if action == "star":
        crit.append("UNFLAGGED")
    if unread_only is True and action != "mark_read":
        crit.append("UNSEEN")
        said.append("that are unread")
    if s_word:
        crit += ["FROM", _q(s_word)]
        said.append(f"from \"{s_word}\"")
    if subj:
        crit += ["SUBJECT", _q(subj)]
        said.append(f"with \"{subj}\" in the subject")
    if body:
        crit += ["TEXT", _q(body)]
        said.append(f"with \"{body}\" in them")
    if newsletters is True:
        crit += ["HEADER", "List-Unsubscribe", '""']
        said.append("that are newsletters or bulk mail (they carry an unsubscribe link)")
    if since:
        crit += ["SINCE", _imap_date(today - timedelta(days=since))]
        said.append(f"from the last {since} day{'s' if since != 1 else ''}")
    if older:
        crit += ["BEFORE", _imap_date(today - timedelta(days=older))]
        said.append(f"older than {older} day{'s' if older != 1 else ''}")
    if action == "mark_read":
        said.append("that are still unread")
    if action == "star":
        said.append("that are not starred yet")
    asked = "emails " + ", ".join(said) if said else "emails"

    conn = None
    try:
        conn = (connect or _connect)(st)
        typ, _ = conn.select(_q(st.mailbox), readonly=True)
        if typ != "OK":
            return refused(f"the mail server would not open the folder \"{st.mailbox}\"")
        validity = _uidvalidity(conn)
        if not validity:
            return refused("the mail server did not say whether its folder numbers are "
                           "stable (UIDVALIDITY), so Jarvis cannot tidy safely")
        typ, dat = conn.uid("SEARCH", *crit)
        if typ != "OK":
            return refused("the mail server could not run that search")
        uids = [int(x) for x in _text((dat or [b""])[0]).split() if x.isdigit()]
        if not uids:
            return refused(f"no emails match that ({asked}) - nothing to do")
        if len(uids) > MAX_EMAILS:
            return refused(
                f"too many at once: {len(uids)} emails match, and one card can show at "
                f"most {MAX_EMAILS} in full (a card never shows less than everything it "
                f"changes). Narrow it - one sender, fewer days - or do it in rounds",
                matched=len(uids))
        items, left_out = [], 0
        for uid in uids:
            got = _fetch_head(conn, uid, "FROM SUBJECT DATE MESSAGE-ID")
            if got is None:
                continue
            flags, head = got
            msg = email.message_from_string(head)
            mid = _msgid_of(head)
            if action in MOVES and not mid:
                left_out += 1
                continue
            frm = _clean(sender_name(msg.get("From") or ""), 60) or "(no sender)"
            sub = _clean(_hide(_clean(_decode(msg.get("Subject")), 200)), 200) or "(no subject)"
            items.append(Item(uid=uid, message_id=mid, sender=frm, subject=sub,
                              date=_shown_date(_decode(msg.get("Date")), today),
                              seen="\\seen" in flags, flagged="\\flagged" in flags))
        if not items:
            return refused("none of the matching emails could be read, or none can be put "
                           "back after a move (no message id) - nothing to do",
                           left_out=left_out)
        p = Plan(action=action, user=st.user, host=st.host, port=st.port, mailbox=st.mailbox,
                 uidvalidity=validity, asked=asked, items=tuple(items), left_out=left_out,
                 matched=len(uids))
        p = replace(p, digest=fingerprint(p))
        if len(json.dumps({"text": describe(p)})) > CARD_BUDGET:
            return refused(
                f"too many at once: {len(items)} emails match, and the card that lists "
                f"every one of them would be too long to read in full. Narrow it - one "
                f"sender, fewer days - or do it in rounds", matched=len(uids))
        return p
    except _Refused as exc:
        return refused(f"the emails could not be looked at: {exc}")
    except Exception as exc:
        return refused(f"the mail server could not be searched ({type(exc).__name__})")
    finally:
        if conn is not None:
            _logout(conn)


def describe(p: Plan) -> str:
    """The card text: what happens, the account, and EVERY email - sender,
    subject, date, numbered - then what saying no costs. Never a summary."""
    if not p.ready:
        return (f"Jarvis would like to tidy your inbox, but {p.problem}. Nothing would be "
                f"changed.")
    name, question, _past = ACTIONS[p.action]
    n = len(p.items)
    lines = [
        question.format(these="this email" if n == 1 else f"these {n} emails"),
        f"Nothing changes unless you approve. For {UNDO_MINUTES} minutes after, one tap on "
        f"Undo puts {'it' if n == 1 else 'every one'} back exactly as it was.",
        "",
        f"You asked for: {p.asked}.",
        WHAT_IT_DOES[p.action],
        f"Account: {p.user}, folder \"{p.mailbox}\" on {p.host}.",
        "",
        "The email:" if n == 1 else f"The emails ({n}):",
    ]
    for n, i in enumerate(p.items, 1):
        lines.append(f"{n}. {_clean(i.sender, _MAX_SENDER_ON_CARD)} - "
                     f"{_clean(i.subject, _MAX_SUBJECT_ON_CARD)} - {i.date}")
    if p.left_out:
        lines.append(f"Left out: {p.left_out} email{'s' if p.left_out != 1 else ''} with no "
                     f"message id, because Jarvis could not promise to put "
                     f"{'it' if p.left_out == 1 else 'them'} back.")
    lines += [
        "",
        f"Jarvis logs in as {p.user}; your password goes to that server and nowhere else.",
        f"If you say no: {IF_REFUSED}",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------
#   Whether the owner's settings let a tidy happen at all
# --------------------------------------------------------------------------


def tier_of(action: str) -> str:
    try:
        return str(fw.action_tier(action)) if fw is not None else "ask"
    except Exception as exc:
        return f"unreadable ({type(exc).__name__})"


def tier_problem(tier_of: Callable[[str], str] = tier_of) -> str:
    """"" when a tidy can be asked about, else why not. It acts only on tier
    "ask": "auto" or "notify" would change the mailbox with nobody asked."""
    tier = tier_of(ACTION)
    if tier != "ask":
        if tier == "never":
            return (f"tidying the inbox is switched off on this PC ({ACTION} is \"never\" in "
                    f"jarvis-framework.toml's [autonomy.tiers])")
        return (f"{ACTION} is tier {tier!r} in jarvis-framework.toml, which would change the "
                f"mailbox without asking anyone; every tidy needs the owner's yes on a card, "
                f"so nothing is done until it is \"ask\"")
    return ""


def read_problem(tier_of: Callable[[str], str] = tier_of) -> str:
    """"" when Jarvis may look at the inbox to find the emails, else why not.
    plan() reads their From, Subject and Date lines BEFORE the card exists
    (the card has to list every email), so it may only do that where reading
    email is allowed without a card of its own."""
    tier = tier_of(READ_ACTION)
    if tier in ("auto", "notify"):
        return ""
    if tier == "never":
        return ("reading your email is switched off on this PC, and Jarvis has to look at "
                "the emails to list them on the card")
    return ("reading your email asks first on this PC, and Jarvis has to look at the emails "
            "to list them on the card - so tidying is not offered. Ask Jarvis to check your "
            "email first, or set email_read to \"auto\" under 'What asks first'")


def _tools_enabled() -> set:
    try:
        cfg = fw.load_framework() if fw is not None else {}
        return set((cfg.get("tools") or {}).get("enabled") or [])
    except Exception:
        return set()


def view(*, tools_enabled: Optional[Callable[[], set]] = None,
         tier_of: Callable[[str], str] = tier_of) -> dict:
    """Whether tidying is set up, in one plain line (the What-asks-first page
    and the status use it). Never the password."""
    st = settings()
    on = TOOL in (tools_enabled or _tools_enabled)()
    tier_why = tier_problem(tier_of)
    read_why = read_problem(tier_of)
    if st.problem:
        state, said = "not_set_up", f"Not set up: {st.problem}."
    elif tier_why:
        state = "off" if tier_of(ACTION) == "never" else "refused"
        said = f"Set up, but {tier_why}."
    elif read_why:
        state, said = "no_reading", f"Set up, but {read_why}."
    elif not on:
        state = "tool_off"
        said = (f"Set up. Jarvis does not offer to tidy until \"{TOOL}\" is added to "
                f"[tools].enabled in jarvis-framework.toml on the PC.")
    else:
        state = "ready"
        said = (f"Ready: archive, star, mark as read or move to Trash, one approval card "
                f"listing every email, {UNDO_MINUTES} minutes to undo. Nothing is ever "
                f"deleted for good.")
    return {"state": state, "ready": state == "ready", "said": said, "tool_enabled": on}


# --------------------------------------------------------------------------
#   The folders: which one is Archive, Trash and (Gmail) All Mail
# --------------------------------------------------------------------------

_LIST_LINE = re.compile(r'^\((?P<flags>[^)]*)\)\s+(?:"(?:[^"\\]|\\.)*"|NIL)\s+'
                        r'(?:"(?P<qname>(?:[^"\\]|\\.)*)"|(?P<name>\S+))\s*$')


def _folders(conn) -> list:
    """[(flags as a lower-case set, name)] from LIST. Names Jarvis could not
    use safely are left out."""
    try:
        typ, dat = conn.list()
    except Exception:
        return []
    out = []
    if typ != "OK":
        return out
    for raw in dat or []:
        if not raw:
            continue
        m = _LIST_LINE.match(_text(raw).strip())
        if not m:
            continue
        name = m.group("qname")
        name = name.replace('\\"', '"').replace("\\\\", "\\") if name is not None \
            else m.group("name")
        if name and _SAFE_NAME.match(name):
            out.append(({f.lower() for f in m.group("flags").split()}, name))
    return out


def _find_folder(folders: list, flag: str, common: tuple) -> str:
    """The folder the server flags with `flag` (RFC 6154 special-use), else
    one of the common plain names that really is in the list - never one
    that is not there, never a guess."""
    for flags, name in folders:
        if flag in flags:
            return name
    names = {n.lower(): n for _f, n in folders}
    for c in common:
        if c.lower() in names:
            return names[c.lower()]
    return ""


# --------------------------------------------------------------------------
#   Doing it: a move is a MOVE, or a copy first and one message removed
# --------------------------------------------------------------------------

_COPYUID = re.compile(r"COPYUID\s+\d+\s+[\d:,]+\s+(\d+)\b", re.I)


class _Refused(Exception):
    """A reason of ours, in plain words, that nothing was changed."""


def _gmail_labels(conn, uid: int, sign: str, label: str) -> None:
    typ, _ = conn.uid("STORE", str(uid), f"{sign}X-GM-LABELS", f"({label})")
    if typ != "OK":
        raise RuntimeError("label change refused")


def _move_by_copy(conn, uid: int, dst: str) -> Optional[int]:
    """The fallback for a server with no MOVE: copy, and only once the server
    says the copy is done, mark THAT ONE message \\Deleted and `UID EXPUNGE`
    it (UIDPLUS) - so nothing else marked \\Deleted in the folder is touched.
    This is the only place this module ever sets \\Deleted, and the copy
    already sits in the destination. Returns the new UID when the server
    says it (COPYUID)."""
    typ, dat = conn.uid("COPY", str(uid), _q(dst))
    if typ != "OK":
        raise RuntimeError("copy refused")
    m = _COPYUID.search(" ".join(_text(x) for x in (dat or [])))
    new_uid = int(m.group(1)) if m else None
    typ, _ = conn.uid("STORE", str(uid), "+FLAGS.SILENT", "(\\Deleted)")
    if typ == "OK":
        typ, _ = conn.uid("EXPUNGE", str(uid))
    if typ != "OK":
        try:
            conn.uid("STORE", str(uid), "-FLAGS.SILENT", "(\\Deleted)")
        except Exception:
            pass
        raise RuntimeError("could not remove the original after copying")
    return new_uid


def _set_flag(conn, uid: int, flag: str) -> None:
    """Add `flag` to the selected folder's message `uid`. imaplib raises only
    on BAD, so a NO (a read-only folder, a permission refusal) comes back as a
    plain answer: it is checked here, or the email would be counted as changed
    and an Undo record kept for a change that never happened (bug audit
    2026-09-29). The move paths already check theirs."""
    typ, _ = conn.uid("STORE", str(uid), "+FLAGS.SILENT", flag)
    if typ != "OK":
        raise RuntimeError("the server refused to change the flag")


def _move(conn, caps: set, uid: int, dst: str) -> Optional[int]:
    """Move the selected folder's message `uid` to `dst`. Returns its new
    UID when the server tells us."""
    if "MOVE" in caps:
        typ, dat = conn.uid("MOVE", str(uid), _q(dst))
        if typ != "OK":
            raise RuntimeError("move refused")
        m = _COPYUID.search(" ".join(_text(x) for x in (dat or [])))
        return int(m.group(1)) if m else None
    return _move_by_copy(conn, uid, dst)


def _needs_safe_move(caps: set, gmail: bool) -> str:
    if gmail or "MOVE" in caps or "UIDPLUS" in caps:
        return ""
    return ("this mail server can neither move an email in one step (MOVE) nor remove just "
            "one after copying it (UIDPLUS), so Jarvis cannot move emails on it without "
            "risking other mail - nothing was changed")


# --------------------------------------------------------------------------
#   State: the Undo records (in memory only), one lock for the mailbox work
# --------------------------------------------------------------------------

_LOCK = threading.Lock()
#: Held while approved changes are made and while Undo runs, so the two
#: never interleave.
_SWITCH = threading.Lock()
_STATE: dict = {"undo": [], "last": None}


def _count(n: int, one: str, many: Optional[str] = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def _said(action: str, n: int) -> str:
    return ACTIONS[action][2].format(n=_count(n, "email"))


def _purge(token: str) -> None:
    """The ten minutes are up: the record is dropped, for good."""
    with _LOCK:
        keep = [u for u in _STATE["undo"] if u["token"] != token]
        gone = len(keep) != len(_STATE["undo"])
        _STATE["undo"] = keep
    if gone:
        _audit("email.tidy.kept", {})


def _expire(now: float) -> None:
    with _LOCK:
        live = [u for u in _STATE["undo"] if u["until"] > now]
        gone = len(live) != len(_STATE["undo"])
        _STATE["undo"] = live
    if gone:
        _audit("email.tidy.kept", {})


def _undo_full_words(now: float) -> str:
    """Empty when there is room for one more tidy; else the plain sentence saying
    why not. Up to MAX_UNDO tidies wait for Undo at once, and a sixth used to push
    the oldest out without a word, so the owner lost an Undo they had been told
    they had for 10 minutes (bug audit 2026-09-29; the owner chose to refuse the
    new tidy instead)."""
    _expire(now)
    with _LOCK:
        full = len(_STATE["undo"]) >= MAX_UNDO
    if not full:
        return ""
    return (f"{MAX_UNDO} earlier tidies can still be undone, and Jarvis keeps at most "
            f"{MAX_UNDO} so none is lost without a word. Wait for one to run out (each "
            f"lasts {UNDO_SECONDS // 60} minutes) or undo one first")


def _undo_view(u: dict, now: float, more: int) -> dict:
    left = max(0, int(u["until"] - now))
    n = len(u["items"])
    name = ACTIONS[u["action"]][0]
    return {"until": int(u["until"]), "seconds_left": left,
            "minutes_left": max(1, -(-left // 60)) if left else 0,
            "count": n, "action": u["action"], "action_name": name, "more": more,
            "said": _said(u["action"], n)}


#: The apps read the status every 20 seconds; whether tidying is set up
#: (Credential Manager reads, the settings file) does not change that fast.
_VIEW_CACHE: dict = {"value": None, "at": 0.0}
_VIEW_TTL = 30.0


def _cached_view() -> dict:
    now = time.monotonic()
    with _LOCK:
        if _VIEW_CACHE["value"] is not None and now - _VIEW_CACHE["at"] < _VIEW_TTL:
            return _VIEW_CACHE["value"]
    v = view()
    with _LOCK:
        _VIEW_CACHE.update(value=v, at=now)
    return v


def status(now: Optional[float] = None) -> dict:
    """GET /api/email/tidy: whether it is set up (one plain line) and the
    newest tidy still open to Undo. Counts and words of ours only - never a
    sender or a subject."""
    now = _now() if now is None else now
    _expire(now)
    with _LOCK:
        undo = list(_STATE["undo"])
        last = dict(_STATE["last"]) if _STATE["last"] else None
    v = _cached_view()
    return {"available": True, "title": WORDS["title"], "state": v["state"],
            "ready": v["ready"], "said": v["said"],
            "undo": _undo_view(undo[-1], now, len(undo) - 1) if undo else None,
            "last": last, "undo_minutes": UNDO_MINUTES, "max_emails": MAX_EMAILS,
            "actions": [{"id": k, "label": v_[0]} for k, v_ in ACTIONS.items()]}


# --------------------------------------------------------------------------
#   Running an approved plan
# --------------------------------------------------------------------------


def _failure(exc: BaseException) -> str:
    """A plain sentence. The exception's own message is never used: it can
    quote the server's reply."""
    if isinstance(exc, _Refused):
        return f"{exc}"
    return f"the mail server stopped answering or refused a change ({type(exc).__name__})"


def _still_there(conn, item: Item) -> Optional[set]:
    """The message's flags when `uid` still holds the same email, else None."""
    got = _fetch_head(conn, item.uid, "MESSAGE-ID")
    if got is None:
        return None
    flags, head = got
    if item.message_id and _msgid_of(head) != item.message_id:
        return None
    return flags


def run(p: Plan, *, approved: bool = False, connect: Optional[Callable] = None,
        now: Optional[float] = None, timer: Optional[Callable] = None) -> dict:
    """Do an approved plan - exactly it, once. `approved` has no default of
    True. `connect` and `timer` are injectable for tests.

    Refused, with nothing changed, when: not approved; the plan has a
    problem; its fingerprint no longer matches; the account or folder in the
    settings is no longer what the card showed; the folder was rebuilt on
    the server since (UIDVALIDITY); or the server cannot do a safe move.
    Each email is checked again just before it is touched - one that was
    moved, deleted or already changed is skipped, never touched blindly.
    Whatever was changed is recorded for Undo, even when something failed
    part of the way."""
    if not approved:
        return {"ok": False, "done": 0, "error": "not approved; nothing was changed"}
    if not p.ready:
        return {"ok": False, "done": 0, "error": f"nothing was changed: {p.problem}."}
    if not p.digest or fingerprint(p) != p.digest:
        return {"ok": False, "done": 0,
                "error": "nothing was changed: the list changed after the card was made, "
                         "so it is not the one that was approved."}
    st = settings()
    if (st.problem or st.user != p.user or st.host != p.host or st.port != p.port
            or st.mailbox != p.mailbox):
        return {"ok": False, "done": 0,
                "error": "nothing was changed: the account or the mail server settings "
                         "changed after the card was shown, so this is not what was "
                         "approved."}
    full = _undo_full_words(_now() if now is None else now)
    if full:
        return {"ok": False, "done": 0, "error": f"nothing was changed: {full}."}
    timer = timer or _timer
    done: list = []
    skipped = 0
    dst = ""
    gmail = False
    conn = None
    failure = ""
    with _SWITCH:
        try:
            _register_with_scrubber(st.user, imap_password())
            conn = (connect or _connect)(st)
            typ, _ = conn.select(_q(p.mailbox))           # for changes: never CLOSEd
            if typ != "OK":
                raise _Refused(f"nothing was changed: the mail server would not open the "
                               f"folder \"{p.mailbox}\"")
            if _uidvalidity(conn) != p.uidvalidity:
                raise _Refused("nothing was changed: the mail server rebuilt that folder "
                               "since the card was made, so its numbers no longer point at "
                               "the same emails. Ask again.")
            caps = _caps(conn)
            gmail = "X-GM-EXT-1" in caps
            if p.action in MOVES:
                why = _needs_safe_move(caps, gmail)
                if why:
                    raise _Refused(f"nothing was changed: {why}")
                folders = _folders(conn)
                if p.action == "trash":
                    dst = _find_folder(folders, "\\trash", _COMMON_TRASH)
                    if not dst:
                        raise _Refused("nothing was changed: Jarvis could not find this "
                                       "account's Trash folder, and does not guess one")
                elif gmail:
                    dst = _find_folder(folders, "\\all", ())
                    if not dst or p.mailbox.upper() != "INBOX":
                        raise _Refused("nothing was changed: on Gmail, Jarvis archives only "
                                       "from the Inbox, and needs to find All Mail")
                else:
                    dst = _find_folder(folders, "\\archive", _COMMON_ARCHIVE)
                    if not dst:
                        raise _Refused("nothing was changed: this account has no Archive "
                                       "folder Jarvis can recognise, and it does not guess "
                                       "one")
                if dst.lower() == p.mailbox.lower():
                    raise _Refused(f"nothing was changed: the emails are already in \"{dst}\"")
            for it in p.items:
                flags = _still_there(conn, it)
                if flags is None:
                    skipped += 1
                    continue
                if p.action == "mark_read":
                    if "\\seen" in flags:
                        skipped += 1
                        continue
                    _set_flag(conn, it.uid, "(\\Seen)")
                    done.append({"uid": it.uid, "id": it.message_id})
                elif p.action == "star":
                    if "\\flagged" in flags:
                        skipped += 1
                        continue
                    _set_flag(conn, it.uid, "(\\Flagged)")
                    done.append({"uid": it.uid, "id": it.message_id})
                elif gmail:
                    if p.action == "trash":
                        typ, _ = conn.uid("COPY", str(it.uid), _q(dst))
                        if typ != "OK":
                            raise RuntimeError("copy to Trash refused")
                    _gmail_labels(conn, it.uid, "-", "\\Inbox")
                    done.append({"uid": it.uid, "id": it.message_id, "new": None})
                else:
                    new_uid = _move(conn, caps, it.uid, dst)
                    done.append({"uid": it.uid, "id": it.message_id, "new": new_uid})
        except Exception as exc:
            failure = _failure(exc)
        finally:
            if conn is not None:
                _logout(conn)
            # Whatever was done is held for Undo, even when something failed
            # part of the way: nothing done here is ever left without it.
            if done:
                token = uuid.uuid4().hex
                at = _now() if now is None else now
                rec = {"token": token, "until": at + UNDO_SECONDS, "action": p.action,
                       "items": done, "mailbox": p.mailbox, "uidvalidity": p.uidvalidity,
                       "dst": dst, "gmail": gmail, "user": p.user, "host": p.host,
                       "port": p.port}
                with _LOCK:
                    stack = _STATE["undo"] + [rec]
                    _STATE["undo"] = stack[-MAX_UNDO:]
                    _STATE["last"] = {"outcome": "done", "at": at,
                                      "message": _said(p.action, len(done))}
                timer(UNDO_SECONDS, lambda tok=token: _purge(tok))
    _audit("email.tidy.done", {"action": p.action, "done": len(done), "skipped": skipped,
                               "failed": bool(failure)})
    if failure and not done:
        return {"ok": False, "done": 0, "skipped": skipped, "error": failure}
    said = _said(p.action, len(done))
    if skipped:
        said += (f" {_count(skipped, 'email')} skipped - already moved, deleted or "
                 f"changed since the card was made.")
    if failure:
        said += f" It stopped part of the way: {failure}."
    said += (f" The owner can undo this for {UNDO_MINUTES} minutes with the Undo button on "
             f"screen.") if done else ""
    return {"ok": not failure, "done": len(done), "skipped": skipped, "action": p.action,
            "undo_minutes": UNDO_MINUTES if done else 0, "said": said,
            **({"error": failure} if failure else {})}


# --------------------------------------------------------------------------
#   Undo: POST /api/email/tidy/undo - one tap, no card
# --------------------------------------------------------------------------


def _find_moved(conn, item: dict) -> Optional[int]:
    """The UID an email has now in the selected folder: the server's own
    COPYUID answer when it gave one (checked against the Message-ID), else
    the newest message there with that Message-ID."""
    if item.get("new"):
        got = _fetch_head(conn, item["new"], "MESSAGE-ID")
        if got is not None and _msgid_of(got[1]) == item["id"]:
            return item["new"]
    if not _MSGID.match(item.get("id") or ""):
        return None
    typ, dat = conn.uid("SEARCH", "HEADER", "Message-ID", _q(item["id"]))
    if typ != "OK":
        return None
    uids = [int(x) for x in _text((dat or [b""])[0]).split() if x.isdigit()]
    return max(uids) if uids else None


def _undo_moves(conn, caps: set, rec: dict, tally: dict) -> None:
    """Put a move back. `conn` is logged in. Each email done or given up on
    leaves rec["items"], so a server that drops part-way leaves exactly what
    is still to do."""
    typ, _ = conn.select(_q(rec["dst"]))
    if typ != "OK":
        raise RuntimeError("could not open the folder they were moved to")
    while rec["items"]:
        it = rec["items"][0]
        uid = _find_moved(conn, it)
        if uid is None:
            tally["lost"] += 1
        else:
            if rec["gmail"]:
                _gmail_labels(conn, uid, "+", "\\Inbox")
                if rec["action"] == "trash":
                    _gmail_labels(conn, uid, "-", "\\Trash")
            else:
                _move(conn, caps, uid, rec["mailbox"])
            tally["restored"] += 1
        rec["items"].pop(0)


def _undo_flags(conn, rec: dict, tally: dict) -> None:
    """Take a flag Jarvis set off again - only where it set it."""
    typ, _ = conn.select(_q(rec["mailbox"]))
    if typ != "OK":
        raise RuntimeError("could not open the folder")
    if _uidvalidity(conn) != rec["uidvalidity"]:
        tally["lost"] += len(rec["items"])
        rec["items"].clear()
        return
    flag = "\\Seen" if rec["action"] == "mark_read" else "\\Flagged"
    while rec["items"]:
        it = rec["items"][0]
        got = _fetch_head(conn, it["uid"], "MESSAGE-ID")
        if got is None or (it["id"] and _msgid_of(got[1]) != it["id"]):
            tally["lost"] += 1
        else:
            conn.uid("STORE", str(it["uid"]), "-FLAGS.SILENT", f"({flag})")
            tally["restored"] += 1
        rec["items"].pop(0)


def undo(*, connect: Optional[Callable] = None, now: Optional[float] = None) -> tuple:
    """Put back exactly what the newest tidy still open to Undo changed."""
    now = _now() if now is None else now
    _expire(now)
    with _SWITCH:
        with _LOCK:
            if not _STATE["undo"]:
                return 409, {"ok": False, "error": (
                    "There is nothing to undo - the 10 minutes are up, or it was already "
                    "undone.")}
            rec = _STATE["undo"].pop()
        st = settings()
        if (st.problem or st.user != rec["user"] or st.host != rec["host"]
                or st.port != rec["port"]):
            with _LOCK:
                _STATE["undo"].append(rec)
            return 409, {"ok": False, "error": (
                "The mail account or server settings changed since the tidy, so Jarvis "
                "cannot safely put the emails back from here. Undo them in your mail app.")}
        tally = {"restored": 0, "lost": 0}
        conn = None
        try:
            conn = (connect or _connect)(st)
            if rec["action"] in MOVES:
                _undo_moves(conn, _caps(conn), rec, tally)
            else:
                _undo_flags(conn, rec, tally)
        except Exception as exc:
            # Nothing is lost: what is still to do goes back for another try
            # while its ten minutes last.
            if rec["items"]:
                with _LOCK:
                    _STATE["undo"].append(rec)
            _audit("email.tidy.undo_failed", {"error": type(exc).__name__,
                                              "restored": tally["restored"]})
            how = (str(exc) if isinstance(exc, _Refused)
                   else f"could not reach the mail server ({type(exc).__name__})")
            part = (f" {_count(tally['restored'], 'email')} "
                    f"{'was' if tally['restored'] == 1 else 'were'} put back before it stopped."
                    if tally["restored"] else "")
            return 503, {"ok": False, "restored": tally["restored"], "error": (
                f"Jarvis {how}.{part} Try again - what is left can still be undone until "
                f"the 10 minutes are up.")}
        finally:
            if conn is not None:
                _logout(conn)
        restored, lost = tally["restored"], tally["lost"]
        said = f"Put back {_count(restored, 'email')}." if restored else "Nothing was put back."
        if lost:
            said += (f" {_count(lost, 'email')} could not be put back - you moved or deleted "
                     f"{'it' if lost == 1 else 'them'} since, or the server changed.")
        with _LOCK:
            _STATE["last"] = {"outcome": "undone", "at": now, "message": said}
    _audit("email.tidy.undone", {"restored": restored, "lost": lost})
    return 200, {"ok": True, "restored": restored, "not_restored": lost, "message": said}


# --------------------------------------------------------------------------
#   The routes
# --------------------------------------------------------------------------


def handle_get(route: str, **kw) -> tuple:
    if route == ROUTE:
        return 200, status(kw.get("now"))
    if route == UNDO:
        return 405, {"ok": False, "error": "use POST for this"}
    return 404, {"ok": False, "error": "no such route"}


def handle_post(route: str, body, **kw) -> tuple:
    if route == UNDO:
        if body is not None and not isinstance(body, dict):
            return 400, {"ok": False, "error": "Send a JSON object."}
        return undo(**{k: kw[k] for k in ("connect", "now") if k in kw})
    if route == ROUTE:
        return 405, {"ok": False, "error": (
            "Tidying is asked for in chat - Jarvis lists the emails on an approval card. "
            "Use GET for the status.")}
    return 404, {"ok": False, "error": "no such route"}


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_GET` and `do_POST` so these routes are answered
    here, after the server's own origin and token checks. Every other
    request goes straight to the original. Returns the banner line."""
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(post0, "_jarvis_inbox_tidy", False):
        return "  inbox      Inbox tidy (already on)"

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
        if route not in ROUTES:
            return get0(self)
        if not _allowed(self):
            return None
        try:
            code, out = handle_get(route)
        except Exception as exc:
            code, out = 503, {"available": False, "error": type(exc).__name__}
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
        try:
            code, out = handle_post(route, body)
        except Exception as exc:
            code, out = 503, {"available": False, "error": type(exc).__name__}
        return self._send(code, out)

    do_GET._jarvis_inbox_tidy = True
    do_POST._jarvis_inbox_tidy = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    return (f"  inbox      Inbox tidy: one card listing every email, {UNDO_MINUTES} "
            f"minutes to undo")


def _reset_for_tests() -> None:
    with _LOCK:
        _STATE.update(undo=[], last=None)
        _VIEW_CACHE.update(value=None, at=0.0)
