"""jarvis_email_draft.py - lets Jarvis SAVE one email DRAFT into the owner's
own Drafts folder, after the owner has read all of it on an approval card.
Nothing is ever sent by this module - a draft is not mailed to anyone until
the owner opens it themselves, in their own mail program, and chooses to.

THE OWNER'S DECISION (CLAUDE.md, "Decided 2026-09-27, the owner's answers to
docs/OWNER-QUESTIONS-2026-09-27.md"): "Email drafts: a card every time,
showing the full draft, before any text goes to the owner's Drafts folder."
`draft_email` was already tier "ask" in the shipped jarvis-framework.toml -
its comment used to say "not built yet; I53"; this module, `draft-email.patch`
and the `draft_email` tool in jarvis_agent.py are that build, and the
comment now says so.

THE SAME SHAPE AS jarvis_email_send.py, DELIBERATELY - the closest existing
feature (one email, one card, exact content, local model only, the same
account as reading email):
    plan(to, cc, subject, body, reply_to_message_id=None)
                        Works out exactly what would be SAVED (never sent).
                        Checks every address given, the length of everything,
                        and the settings. Opens no socket. Returns a Plan -
                        which never holds the password.
    describe(plan)      The card text: To, Cc, Subject and the WHOLE draft,
                         word for word, then where it is saved and what
                         saying no costs.
    run(plan, approved) Saves exactly that plan, once, by IMAP APPEND to the
                        account's \\Drafts special-use mailbox ONLY - never
                        anywhere else, and never over SMTP: this module does
                        not import smtplib and cannot send mail. `approved`
                        has no default of True. A plan whose content changed
                        after it was made (its fingerprint no longer
                        matches), or whose account or server settings
                        changed since, is refused: nothing is saved.

RECIPIENTS ARE OPTIONAL FOR A DRAFT - THE ONE REAL DIFFERENCE FROM SENDING.
Sending needs a real "who to" before anything happens; a draft does not.
"Draft a reply to Sam" often means the model has a rough subject and body in
mind and no confirmed address yet - the owner fills in or corrects the
address later, in their own mail program, before ever sending it. So `plan()`
accepts an empty `to` and `cc` (each address given IS still checked - a typo
is still a typo), and only refuses when the draft would be completely empty:
no recipient, no subject and no text at all, which is nothing to save. Every
other cap (10 people, a 200-character subject, a 2,500-character body, no
attachments, no invisible characters) is unchanged from sending, for the same
reason: the gate keeps 4,000 characters on a card, and a card never shows
less than everything a draft holds.

NO ATTACHMENTS - ENFORCED BY WHAT THIS MODULE DOES NOT HAVE, NOT BY A CHECK.
`plan()` has no `attachments` parameter (test_email_draft.py checks this the
same way test_email_send.py checks jarvis_email_send.plan for the same
thing: `"attach" not in plan.__code__.co_varnames`). jarvis_agent.py's
`_prepare_draft_email` reads only `to`, `cc`, `subject`, `body` and
`reply_to_message_id` out of the model's arguments; an "attachments" key the
model adds anyway is simply never looked at, by either this module or the
tool wiring - the same reason jarvis_email_send.py has no attachments today.

WHY THIS IS AN IMAP WRITE, NOT A NEW LANE (docs/ARCHITECTURE.md section 4).
Reading email (jarvis_email.py) and sending it (jarvis_email_send.py) both
already reach the owner's own mail server, on the same account, with the
same password; this is the first WRITE to the mailbox itself (every read
uses EXAMINE and BODY.PEEK - "No STORE, COPY, MOVE" - jarvis_email.py's own
docstring), so it earns its own row in that table even though it is not a
new destination: docs/ARCHITECTURE.md section 4, "saving an email draft".

SETTINGS - THE SAME ACCOUNT AS READING (AND SENDING) EMAIL, NOTHING NEW.
This module reaches the account over IMAP, exactly like jarvis_email.py -
not over SMTP like jarvis_email_send.py, because a draft is a mailbox write,
not something posted to a sending server. So it reads jarvis_email.py's own
four settings, fresh from the environment on every call, never cached, never
written to disk:
    JARVIS_IMAP_HOST        the mail server (also used for reading)
    JARVIS_IMAP_PORT        993 (the default) if not set
    JARVIS_IMAP_USER        the account; also the draft's own From address
    JARVIS_IMAP_PASSWORD    the password (the same one reading and sending
                            already use)
Nothing new to set up for an account that can already read its mail.

WHICH MAILBOX IS "DRAFTS" - FOUND, NEVER GUESSED FIRST.
A Drafts folder's real name differs by provider - "Drafts" on most, but
"[Gmail]/Drafts" on Gmail. Rather than hard-code a name, `run()` asks the
server which mailbox IT calls Drafts: IMAP's LIST command returns each
mailbox's special-use flag (RFC 6154), and Gmail (like most modern
providers) already includes `\\Drafts` on the one that means Drafts, without
needing the newer SPECIAL-USE extension. Only when no server-flagged mailbox
is found does `_find_drafts_mailbox` fall back to trying a short list of
common plain names. This can only happen with a live connection, so it is
found at `run()` time, not `plan()` time - `plan()` opens no socket, the
same invariant as every other plan in this project, so a plan can say
"ready" and `run()` can still refuse if the server turns out to have no
Drafts folder `_find_drafts_mailbox` recognises. Mailbox names with
characters outside the safe printable ASCII set are refused rather than
guessed at: IMAP mailbox names outside plain ASCII need modified UTF-7
encoding, which this first version does not implement, and silently
mis-encoding a folder name is worse than saying so.

THE MESSAGE ITSELF.
Built the same way jarvis_email_send.message() builds a real email - From,
To (if any), Cc (if any), Subject (if any), Date, a Message-ID, the text as
plain UTF-8 encoded 7-bit-safe, and (for a reply) In-Reply-To/References -
then APPENDed with the standard `\\Draft` IMAP flag, so the owner's own mail
program shows it as a draft, editable, not as new unread mail.

THE PASSWORD (CLAUDE.md rule 3) - the same care as jarvis_email_send.py:
read from the environment at the moment of saving and nowhere else; sent to
the account's own IMAP server only, inside the encrypted connection (the
server's certificate is checked, `jarvis_email.tls_context`); never in a
Plan, a card, a result, an error or an event; never logged (the variable's
name holds "PASSWORD", so jarvis_scrub hides its value by value, and IMAP
LOGIN's base64 forms are registered with the scrubber too); never handed to
a program Jarvis starts.

WHAT THIS FIRST VERSION DOES NOT DO, said plainly
  - No attachments. Plain text only (no HTML).
  - At most MAX_RECIPIENTS people across To and Cc; no Bcc, for the same
    reason as sending - a hidden recipient is the one thing a card cannot
    show well, even though a draft's recipients are not yet final.
  - Plain ASCII addresses only (no internationalised addresses), and a
    Drafts mailbox name outside plain ASCII is refused rather than guessed.
  - A body of at most MAX_BODY_CHARS characters, for the same reason as
    sending: the gate keeps 4,000 characters of a card, and a card never
    shows less than everything it saves.
  - Never retries. A save that failed half way is reported as "may have been
    saved - check your Drafts folder", never tried again.
  - Cannot edit or delete a draft it saved earlier - only ever appends a new
    one. Managing drafts stays in the owner's own mail program.

Standard library only (imaplib, ssl already covered by jarvis_email.py,
email). Opens nothing on import. Never imports smtplib - this module cannot
send mail by construction, not only by a check.
"""
from __future__ import annotations

import base64
import hashlib
import os
import re
import time
import unicodedata
from dataclasses import dataclass, field, replace
from email.message import EmailMessage
from email.policy import SMTP as _SMTP
from email.utils import formatdate, make_msgid
from typing import Callable, Optional

#: The account is the one jarvis_email.py reads with - one place for the
#: names, and the SAME ones jarvis_email_send.py already imports.
from jarvis_email import HOST_ENV, PASSWORD_ENV, PORT_ENV, USER_ENV
#: Validation shared with sending, so the two never drift apart on what
#: counts as a plain address or how many people is too many.
from jarvis_email_send import (MAX_ADDRESS_CHARS, MAX_BODY_CHARS, MAX_RECIPIENTS,
                               MAX_SUBJECT_CHARS, valid_address)

#: The gate action every draft is asked under. Tier "ask" in the shipped
#: jarvis-framework.toml, and it must stay "ask" (tier_problem) - it is also
#: on the never-loosened list (jarvis_asks_first.HARD_LIMITS).
ACTION = "draft_email"

#: The model-facing tool name (jarvis_agent.TOOLS) - the same words.
TOOL = "draft_email"

MAX_MESSAGE_ID_CHARS = 250
#: 993 is IMAP over implicit TLS - the same default jarvis_email.py uses.
_DEFAULT_PORT = 993
TIMEOUT = 30.0

#: How the draft is written for the wire - the same reasoning as sending:
#: CRLF line ends, 7-bit only, so it arrives intact through any server.
SMTP_POLICY = _SMTP.clone(cte_type="7bit")

#: What saying no costs. Always on the card.
IF_REFUSED = "nothing is saved, and Jarvis tells you it was not saved."

#: What the result says when a save may or may not have gone through.
MAYBE_SAVED = ("The mail server stopped answering after the draft was handed over, so "
              "Jarvis cannot tell whether it was saved. Check your Drafts folder before "
              "asking again - Jarvis never retries, so it cannot go twice by itself.")

#: The mailbox names tried, in order, ONLY when no server-flagged \\Drafts
#: mailbox is found (see _find_drafts_mailbox). Plain ASCII, most common
#: first; Gmail's own is usually found by its flag before this is needed.
COMMON_DRAFTS_NAMES = ("Drafts", "INBOX.Drafts", "INBOX/Drafts",
                       "[Gmail]/Drafts", "[Google Mail]/Drafts")

#: Mailbox names this module will use as they are. Outside this, a mailbox
#: found by LIST is refused rather than guessed at (see the module docstring,
#: "found, never guessed first").
_SAFE_MAILBOX_RE = re.compile(r"^[\x20-\x7e]+$")


# --------------------------------------------------------------------------
#   Settings - read fresh every call
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Settings:
    sender: str = ""
    host: str = ""
    port: int = _DEFAULT_PORT
    problem: str = ""           # "" when saving a draft is set up

    @property
    def ready(self) -> bool:
        return not self.problem


def settings() -> Settings:
    """How a draft would be saved, from the environment - the same account
    jarvis_email.py reads with. Never the password - only whether one is
    set. Opens nothing."""
    sender = os.environ.get(USER_ENV, "").strip()
    has_password = bool(os.environ.get(PASSWORD_ENV, ""))
    host = os.environ.get(HOST_ENV, "").strip()
    raw_port = os.environ.get(PORT_ENV, "").strip()
    port = _DEFAULT_PORT
    port_problem = ""
    if raw_port:
        try:
            port = int(raw_port)
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            port_problem = f"{PORT_ENV} is not a port number"
            port = _DEFAULT_PORT

    def s(problem: str) -> Settings:
        return Settings(sender, host, port, problem)

    if not host:
        return s(f"{HOST_ENV} is not set - saving a draft uses the same account as "
                 f"reading email, and there is none")
    if not sender:
        return s(f"{USER_ENV} is not set - saving a draft uses the same account as "
                 f"reading email, and there is none")
    if not valid_address(sender):
        return s(f"{USER_ENV} is not an email address, so Jarvis cannot tell which "
                 f"address the draft is from")
    if not has_password:
        return s(f"{PASSWORD_ENV} is not set, so the mail server would refuse the login")
    if port_problem:
        return s(port_problem)
    return s("")


# --------------------------------------------------------------------------
#   The plan - worked out locally, saved by no one yet
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Plan:
    sender: str
    to: tuple
    cc: tuple
    subject: str
    body: str
    in_reply_to: str
    host: str
    port: int
    problem: str = ""
    digest: str = field(default="", compare=False)

    @property
    def ready(self) -> bool:
        return not self.problem

    @property
    def recipients(self) -> tuple:
        return self.to + self.cc

    def as_dict(self) -> dict:
        return {"sender": self.sender, "to": list(self.to), "cc": list(self.cc),
                "subject": self.subject, "body": self.body,
                "in_reply_to": self.in_reply_to, "host": self.host, "port": self.port,
                "problem": self.problem}


def fingerprint(p: Plan) -> str:
    """A fingerprint of everything that would be saved and where. Taken when
    the plan is made; run() takes it again and saves nothing if it differs."""
    parts = [p.sender, "\x1f".join(p.to), "\x1f".join(p.cc), p.subject, p.body,
             p.in_reply_to, p.host, str(p.port)]
    return hashlib.sha256("\x1e".join(parts).encode("utf-8")).hexdigest()


def _as_list(value, name: str):
    """A list of strings from what the model sent; (list, problem). The same
    rule as jarvis_email_send._as_list: one address as a plain string is
    accepted; a comma-separated string is not split, so a mistake is refused
    rather than guessed at."""
    if value is None or value == "":
        return [], ""
    if isinstance(value, str):
        return [value], ""
    if not isinstance(value, (list, tuple)):
        return [], f"{name} must be a list of email addresses"
    if not all(isinstance(v, str) for v in value):
        return [], f"{name} must be a list of email addresses"
    return list(value), ""


#: The same invisible/control character rule as jarvis_email_send.py - a
#: right-to-left override or a Unicode line/paragraph separator could make a
#: card read differently from what is saved.
_INVISIBLE = ("Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp")


def _hidden_chars(text: str, allow: str = "") -> bool:
    return any(unicodedata.category(ch) in _INVISIBLE and ch not in allow for ch in text)


#: <left@right>, printable ASCII, no spaces or angle brackets inside - the
#: same shape jarvis_email_send.py checks a reply's message id against.
_MESSAGE_ID_RE = re.compile(r"^<[\x21-\x3b\x3d\x3f-\x7e]+@[\x21-\x3b\x3d\x3f-\x7e]+>$")


def plan(to=None, cc=None, subject: str = "", body: str = "",
        reply_to_message_id: Optional[str] = None) -> Plan:
    """Work out the one draft this would save. Opens no socket. A plan with
    a `problem` is never saved and needs no card: the problem says why.

    Unlike jarvis_email_send.plan, `to` and `cc` may both be empty - a draft
    does not need a confirmed recipient yet (see the module docstring)."""
    st = settings()

    def refused(problem: str) -> Plan:
        p = Plan(sender=st.sender, to=(), cc=(), subject="", body="", in_reply_to="",
                 host=st.host, port=st.port, problem=problem)
        return replace(p, digest=fingerprint(p))

    to_list, why = _as_list(to, "to")
    if why:
        return refused(why)
    cc_list, why = _as_list(cc, "cc")
    if why:
        return refused(why)
    to_list = [a.strip() for a in to_list]
    cc_list = [a.strip() for a in cc_list]
    bad = [a for a in to_list + cc_list if not valid_address(a)]
    if bad:
        shown = bad[0] if len(bad[0]) <= 80 else bad[0][:77] + "..."
        return refused(f"\"{shown}\" is not a plain email address (like name@example.com). "
                       f"Write each address on its own, with no name or comma")
    seen, dedup_to, dedup_cc = set(), [], []
    for bucket, out in ((to_list, dedup_to), (cc_list, dedup_cc)):
        for a in bucket:
            if a.lower() not in seen:
                seen.add(a.lower())
                out.append(a)
    if len(seen) > MAX_RECIPIENTS:
        return refused(f"that is {len(seen)} people; one draft may hold at most "
                       f"{MAX_RECIPIENTS} (To and Cc together)")

    if not isinstance(subject, str):
        return refused("the subject must be text")
    subject = subject.strip()
    if len(subject) > MAX_SUBJECT_CHARS:
        return refused(f"the subject is {len(subject)} characters; at most "
                       f"{MAX_SUBJECT_CHARS}")
    if subject and _hidden_chars(subject):
        return refused("the subject holds a line break or an invisible character, which "
                       "would make the card read differently from what is saved")

    if not isinstance(body, str):
        return refused("the draft's text must be text")
    body = body.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    if len(body) > MAX_BODY_CHARS:
        return refused(f"the draft is {len(body)} characters; one approval card can show "
                       f"at most {MAX_BODY_CHARS} in full, and a card never shows less "
                       f"than everything it saves. Write it shorter, or the owner can "
                       f"start the draft from their own mail app")
    if body and _hidden_chars(body, allow="\n\t"):
        return refused("the draft's text holds invisible or control characters, which "
                       "would make the card read differently from what is saved")

    if not dedup_to and not dedup_cc and not subject and not body.strip():
        return refused("there is nothing to draft yet - give it a recipient, a subject "
                       "or some text")

    in_reply_to = ""
    if reply_to_message_id not in (None, ""):
        mid = str(reply_to_message_id).strip()
        if not mid.startswith("<"):
            mid = f"<{mid}>"
        if len(mid) > MAX_MESSAGE_ID_CHARS or not _MESSAGE_ID_RE.match(mid):
            return refused("reply_to_message_id is not a message id (like <abc@mail.example.com>)")
        in_reply_to = mid

    p = Plan(sender=st.sender, to=tuple(dedup_to), cc=tuple(dedup_cc), subject=subject,
             body=body, in_reply_to=in_reply_to, host=st.host, port=st.port,
             problem=st.problem and f"saving a draft is not set up on this PC: {st.problem}")
    return replace(p, digest=fingerprint(p))


def describe(p: Plan) -> str:
    """The card text: every recipient given so far, the subject and the
    WHOLE draft - never a summary - then where it is saved and what saying
    no costs. Never sent: the card says so, twice."""
    if not p.ready:
        return (f"Jarvis would like to save an email draft, but {p.problem}. "
                f"Nothing would be saved.")
    lines = [
        "Save this email draft to your Drafts folder? It is only saved if you approve, "
        "exactly as shown - every word is below. Nothing is sent: a draft is never "
        "emailed to anyone until you open it yourself and choose to send it.",
        "",
        f"From: {p.sender}",
        f"To: {', '.join(p.to) if p.to else '(not set yet)'}",
        f"Cc: {', '.join(p.cc) if p.cc else '(nobody)'}",
        f"Subject: {p.subject if p.subject else '(not set yet)'}",
    ]
    if p.in_reply_to:
        lines.append(f"In reply to: {p.in_reply_to}")
    lines += [
        "",
        "---------- the whole draft ----------",
        p.body if p.body else "(no text yet)",
        "---------- end of the draft ----------",
        "",
        "No attachments.",
        f"It is saved to your Drafts folder on {p.host}, port {p.port}, encrypted "
        f"(IMAP over SSL/TLS). Jarvis logs in there as {p.sender}; your password goes "
        f"to that server and nowhere else.",
        "It stays in your Drafts folder until you open it, change it if you like, and "
        "send it yourself - or delete it.",
        "",
        f"If you say no: {IF_REFUSED}",
    ]
    return "\n".join(lines)


def message(p: Plan) -> EmailMessage:
    """The draft itself, built only from the plan: From, To, Cc, Subject and
    the text the card shows, plus the date, a message id and - for a reply -
    the two threading headers. Nothing else. To and Cc are left off
    entirely when the plan has none, rather than an empty header."""
    msg = EmailMessage(policy=SMTP_POLICY)
    msg["From"] = p.sender
    if p.to:
        msg["To"] = ", ".join(p.to)
    if p.cc:
        msg["Cc"] = ", ".join(p.cc)
    if p.subject:
        msg["Subject"] = p.subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=p.sender.rsplit("@", 1)[-1])
    if p.in_reply_to:
        msg["In-Reply-To"] = p.in_reply_to
        msg["References"] = p.in_reply_to
    msg.set_content((p.body or "") + "\n")
    return msg


# --------------------------------------------------------------------------
#   Whether the owner's settings let a draft be saved at all
# --------------------------------------------------------------------------

def tier_of(action: str) -> str:
    try:
        import jarvis_framework as fw
        return str(fw.action_tier(action))
    except Exception as exc:
        return f"unreadable ({type(exc).__name__})"


def tier_problem(tier_of: Callable[[str], str] = tier_of) -> str:
    """"" when a draft can be asked about, else why not, in plain words.
    Saving acts only on tier "ask": "auto" or "notify" would save with
    nobody asked, and a card that could not end in a person deciding is
    never raised."""
    tier = tier_of(ACTION)
    if tier != "ask":
        if tier == "never":
            return (f"saving email drafts is switched off on this PC ({ACTION} is "
                    f"\"never\" in jarvis-framework.toml's [autonomy.tiers])")
        return (f"{ACTION} is tier {tier!r} in jarvis-framework.toml, which would save a "
                f"draft without asking anyone; every draft needs the owner's yes on a "
                f"card, so nothing is saved until it is \"ask\"")
    return ""


def _tools_enabled() -> set:
    try:
        import jarvis_framework as fw
        cfg = fw.load_framework()
        return set((cfg.get("tools") or {}).get("enabled") or [])
    except Exception:
        return set()


def view(*, tools_enabled: Optional[Callable[[], set]] = None,
         tier_of: Callable[[str], str] = tier_of) -> dict:
    """What the Settings line in both apps shows: whether saving a draft is
    set up, from which address, through which server - never the password,
    only whether one is set. `said` is the one line both apps print as it
    is."""
    st = settings()
    on = TOOL in (tools_enabled or _tools_enabled)()
    tier_why = tier_problem(tier_of)
    route = f"from {st.sender} through {st.host}, port {st.port}, encrypted"
    if st.problem:
        state = "not_set_up"
        said = (f"Not set up: {st.problem}. The steps are in backend/README.md, "
                f"\"Email drafts\".")
    elif tier_why:
        state = "off" if tier_of(ACTION) == "never" else "refused"
        said = f"Set up ({route}), but {tier_why}."
    elif not on:
        state = "tool_off"
        said = (f"Set up ({route}). Jarvis does not offer to save drafts until "
                f"\"{TOOL}\" is added to [tools].enabled in jarvis-framework.toml "
                f"on the PC.")
    else:
        state = "ready"
        said = (f"Ready: {route}. Every draft is its own approval card showing all of "
                f"it; there is no \"always allow\".")
    return {
        "available": True,
        "state": state,
        "ready": state == "ready",
        "from": st.sender if valid_address(st.sender) else "",
        "server": st.host,
        "port": st.port,
        "password_set": bool(os.environ.get(PASSWORD_ENV, "")),
        "tool_enabled": on,
        "said": said,
        "limits": {"recipients": MAX_RECIPIENTS, "subject_chars": MAX_SUBJECT_CHARS,
                   "body_chars": MAX_BODY_CHARS, "attachments": False},
    }


def handle_get() -> tuple:
    """GET /api/email/drafting (draft-email.patch)."""
    return 200, view()


# --------------------------------------------------------------------------
#   Finding the Drafts mailbox - a live connection only, never at plan()
# --------------------------------------------------------------------------

#: One LIST response line: (flags) "delimiter" mailbox-name. The name is
#: either a quoted string or a bare atom; a literal ({n}\r\n...) form is not
#: handled - real servers do not use one for a plain folder name.
_LIST_LINE_RE = re.compile(
    r'^\((?P<flags>[^)]*)\)\s+(?:"(?P<delim>[^"]*)"|NIL)\s+'
    r'(?:"(?P<qname>(?:[^"\\]|\\.)*)"|(?P<name>\S+))\s*$')

_DRAFTS_FLAG_RE = re.compile(r"\\Drafts\b", re.IGNORECASE)


class DraftsFolderNotFound(Exception):
    """No mailbox on this account could be recognised as Drafts."""


def _unquote(name: str) -> str:
    return name.replace('\\"', '"').replace("\\\\", "\\")


def _find_drafts_mailbox(conn) -> str:
    """The one mailbox this account calls "Drafts" - found the way a real
    mail client would: IMAP's LIST tells every mailbox its special-use flag
    (RFC 6154), and `\\Drafts` is the one that means Drafts whatever its real
    name is - "Drafts" on most providers, "[Gmail]/Drafts" on Gmail. A short
    list of plain names is tried only when no server-flagged mailbox is
    found. A name outside plain printable ASCII is refused rather than used
    (see the module docstring)."""
    try:
        status, data = conn.list()
    except Exception:
        status, data = None, None
    if status == "OK" and data:
        for raw in data:
            if not raw:
                continue
            line = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
            m = _LIST_LINE_RE.match(line.strip())
            if not m or not _DRAFTS_FLAG_RE.search(m.group("flags") or ""):
                continue
            name = m.group("qname")
            name = _unquote(name) if name is not None else m.group("name")
            if name and _SAFE_MAILBOX_RE.match(name):
                return name
    for candidate in COMMON_DRAFTS_NAMES:
        try:
            status, _resp = conn.select(candidate, readonly=False)
        except Exception:
            continue
        if status == "OK":
            return candidate
    return ""


# --------------------------------------------------------------------------
#   Saving - one connection, one APPEND, never a retry, never smtplib
# --------------------------------------------------------------------------

def _register_with_scrubber(user: str, password: str) -> None:
    """The password's value is already hidden in logs by its variable name
    (jarvis_scrub). IMAP LOGIN sends it base64-encoded too, so those forms
    are registered - belt and braces, since nothing here prints them."""
    try:
        import jarvis_scrub
    except Exception:
        return
    forms = [password, base64.b64encode(password.encode("utf-8")).decode("ascii")]
    for f in forms:
        try:
            jarvis_scrub.register_secret(f)
        except Exception:
            pass


def _default_append(p: Plan, data: bytes, password: str, phase: list) -> dict:
    """The real conversation. `phase` is updated as it goes, so a failure
    can say whether the draft may have been saved. Never touches any
    message but the one it appends; never sends anything anywhere -
    `imaplib` only, the same as jarvis_email.py's reads."""
    import imaplib

    from jarvis_email import tls_context

    phase[0] = "connect"
    conn = imaplib.IMAP4_SSL(p.host, p.port, timeout=TIMEOUT, ssl_context=tls_context(p.host))
    try:
        phase[0] = "login"
        conn.login(p.sender, password)
        phase[0] = "find_drafts"
        mailbox = _find_drafts_mailbox(conn)
        if not mailbox:
            raise DraftsFolderNotFound(
                "Jarvis could not find a Drafts folder on this mail server")
        phase[0] = "append"
        typ, resp = conn.append(mailbox, "(\\Draft)", imaplib.Time2Internaldate(time.time()),
                                data)
        if typ != "OK":
            raise imaplib.IMAP4.error(f"APPEND refused: {resp!r}")
        return {"mailbox": mailbox}
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def _failure(exc: BaseException, phase: str) -> dict:
    """The plain sentence for each way saving can fail. The exception's own
    message is never used for most of these: it can quote the server's
    reply. `DraftsFolderNotFound`'s own message is ours, in plain words, so
    it is shown as it is."""
    name = type(exc).__name__
    if isinstance(exc, DraftsFolderNotFound):
        return {"ok": False, "saved": False, "error": f"not saved: {exc}."}
    if phase == "login":
        words = ("the mail server refused the login. For Gmail, check the app "
                 "password in JARVIS_IMAP_PASSWORD")
    elif phase in ("connect",):
        words = "the mail server could not be reached"
    elif phase == "find_drafts":
        words = "the mail server could not be asked which folder is Drafts"
    else:
        words = f"saving the draft failed ({name})"
    if phase == "append":
        # Once APPEND is sent, only an ANSWER from the server (a refusal)
        # proves it did not go. A dropped connection or a timeout there
        # proves nothing either way - so it is said so, and never retried.
        return {"ok": False, "saved": "unknown", "error": f"{MAYBE_SAVED} ({name})"}
    return {"ok": False, "saved": False, "error": f"not saved: {words} ({name})."}


def _audit(event: str, detail: dict) -> None:
    """Counts only - never an address, a subject or a word of the text."""
    try:
        import jarvis_framework as fw
        fw.audit_log(event, detail)
    except Exception:
        pass


def run(p: Plan, *, approved: bool = False,
       append: Optional[Callable[[Plan, bytes, str, list], dict]] = None) -> dict:
    """Save an approved plan - exactly it, once, to the account's Drafts
    folder only. `approved` has no default of True. `append` is injectable
    for tests; the default is `_default_append`.

    Refused, with nothing saved, when: not approved; the plan has a problem;
    its fingerprint no longer matches (its content changed after the card
    was made); the account or server in the settings is no longer what the
    card showed; or the password is gone."""
    if not approved:
        return {"ok": False, "saved": False, "error": "not approved; nothing was saved"}
    if not p.ready:
        return {"ok": False, "saved": False, "error": f"not saved: {p.problem}."}
    if not p.digest or fingerprint(p) != p.digest:
        return {"ok": False, "saved": False,
                "error": "not saved: the draft changed after the card was made, so it is "
                         "not the one that was approved. Nothing was saved."}
    now = settings()
    if now.problem or now.sender != p.sender or now.host != p.host or now.port != p.port:
        return {"ok": False, "saved": False,
                "error": "not saved: the account or the mail server settings changed after "
                         "the card was shown, so this is not what was approved. Nothing "
                         "was saved."}
    password = os.environ.get(PASSWORD_ENV, "")
    if not password:
        return {"ok": False, "saved": False, "error": f"not saved: {PASSWORD_ENV} is not set."}
    _register_with_scrubber(p.sender, password)
    data = message(p).as_bytes(policy=SMTP_POLICY)
    phase = ["start"]
    try:
        result = (append or _default_append)(p, data, password, phase)
    except Exception as exc:
        out = _failure(exc, phase[0])
        _audit("email_draft_failed", {"phase": phase[0], "error": type(exc).__name__,
                                      "saved": out.get("saved")})
        return out
    mailbox = result.get("mailbox", "") if isinstance(result, dict) else ""
    _audit("email_draft_saved", {"chars": len(p.body), "has_to": bool(p.to),
                                 "has_subject": bool(p.subject)})
    return {"ok": True, "saved": True, "to": list(p.to), "cc": list(p.cc), "mailbox": mailbox,
            "said": f"Saved to your Drafts folder ({mailbox})." if mailbox
                    else "Saved to your Drafts folder."}
