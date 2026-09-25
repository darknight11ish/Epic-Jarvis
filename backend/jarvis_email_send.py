"""jarvis_email_send.py - lets Jarvis SEND one email, from the owner's own
account, after the owner has read all of it on an approval card.

THE OWNER'S DECISION (CLAUDE.md, "Decided 2026-09-25, after the audit against
Meta's Muse"): Jarvis may send email, ONE approval card per email, the card
showing the exact recipients, subject and full text; never an "always
allow"; the card says plainly when the conversation has read outside text.
Sending is its own named way out of the PC (docs/ARCHITECTURE.md section 4).

jarvis_email.py stays read-only. Its docstring said sending "would need its
own plan, its own card, and its own explicit decision to build"; this module
is that plan, the card is below, and the decision is the owner's line above.

THE PERMISSION MODEL (docs/ARCHITECTURE.md section 3), the same split as
every other module that can reach outside the PC:
    plan(to, cc, subject, body, reply_to_message_id=None)
                        Works out exactly what would be sent, from whom,
                        through which server. Checks every address, the
                        length of everything, and the settings. Opens no
                        socket. Returns a Plan - which never holds the
                        password.
    describe(plan)      The card text: From, To, Cc, Subject and the WHOLE
                        email, word for word, then how it would travel and
                        what saying no costs.
    run(plan, approved) Sends exactly that plan, once. `approved` has no
                        default of True. A plan whose content changed after
                        it was made (its fingerprint no longer matches), or
                        whose account or server settings changed since, is
                        refused: nothing is sent.

Which PERSON approves is the caller's business: jarvis_agent.py puts every
send_email call to jarvis_gate under ACTION ("send_email", tier "ask" in the
shipped jarvis-framework.toml) and runs it only when the verdict records a
person saying yes (NEEDS_A_PERSON). A tier that would let an email through
with nobody asked is refused before any card is raised (`tier_problem`).

SETTINGS - THE SAME ACCOUNT AS READING EMAIL
Nothing new to set up for most accounts. The sender, user name and password
are the ones jarvis_email.py already reads:
    JARVIS_IMAP_USER        the account; also the From address (it must be
                            an email address)
    JARVIS_IMAP_PASSWORD    the password (for Gmail, the same app password)
    JARVIS_IMAP_HOST        used only to work out the sending server when
                            JARVIS_SMTP_HOST is not set: "imap.X" -> "smtp.X"
                            (imap.gmail.com -> smtp.gmail.com)
Optional, only when that guess is wrong:
    JARVIS_SMTP_HOST        the sending server, e.g. smtp.office365.com
    JARVIS_SMTP_PORT        465 (the default) or 587
    JARVIS_SMTP_TLS         "ssl" (the default on 465: encrypted from the
                            first byte), "starttls" (the default on any other
                            port: the server must offer to encrypt, or
                            nothing is sent) or "off" - allowed ONLY to this
                            PC or the owner's own networks (a local relay or
                            a mail bridge), never across the internet, the
                            same rule as plain http:// to Home Assistant
                            (jarvis_local_http.plain_http_problem).
All read fresh from the environment on every call, never cached, never
written to disk.

THE PASSWORD (CLAUDE.md rule 3)
  - read from the environment at the moment of sending, and nowhere else;
  - sent to the sending server only, inside the encrypted connection (or,
    with "off", only to a server on this PC or the owner's own networks);
    the server's certificate is checked (ssl.create_default_context());
  - never in a Plan, a card, a result, an error or an event: a failure is
    told by the exception's NAME and a sentence of ours, never its message;
  - never logged: smtplib's debug output stays off, the variable's name
    holds "PASSWORD" so jarvis_scrub hides its value by value, and the
    base64 forms SMTP login sends are registered with the scrubber too;
  - never handed to a program Jarvis starts: jarvis_child_env drops every
    name holding PASSWORD, so a shell command never sees it.

WHAT THIS FIRST VERSION DOES NOT DO, said plainly
  - No attachments. Plain text only (no HTML).
  - At most MAX_RECIPIENTS people across To and Cc; no Bcc (a hidden
    recipient is the one thing a card cannot show well).
  - Plain ASCII addresses only (no internationalised addresses).
  - A body of at most MAX_BODY_CHARS characters: the approval gate keeps
    4,000 characters of a card, and the owner's rule is that a card shows
    EVERYTHING it authorises, so a longer email is refused, never cut. The
    agent refuses a card that would not fit whole for the same reason.
  - Never retries. A send that failed half way is reported as "may have
    been sent - check your Sent folder", never tried again: a retry could
    send the email twice.
  - The copy is not saved to the Sent folder by Jarvis. Gmail files it there
    by itself; other providers may not.

Standard library only (smtplib, ssl, email). Opens nothing on import.
"""
from __future__ import annotations

import base64
import hashlib
import os
import re
import smtplib
import ssl
import unicodedata
from dataclasses import dataclass, field, replace
from email.message import EmailMessage
from email.policy import SMTP as _SMTP
from email.utils import formatdate, make_msgid
from typing import Callable, Optional

#: The account is the one jarvis_email.py reads with - one place for the names.
from jarvis_email import HOST_ENV as IMAP_HOST_ENV, PASSWORD_ENV, USER_ENV

SMTP_HOST_ENV = "JARVIS_SMTP_HOST"
SMTP_PORT_ENV = "JARVIS_SMTP_PORT"
SMTP_TLS_ENV = "JARVIS_SMTP_TLS"

#: The gate action every email is asked under. Tier "ask" in the shipped
#: jarvis-framework.toml, and it must stay "ask" (tier_problem).
ACTION = "send_email"

#: The model-facing tool name (jarvis_agent.TOOLS) - the same words.
TOOL = "send_email"

MAX_RECIPIENTS = 10
MAX_SUBJECT_CHARS = 200
MAX_BODY_CHARS = 2500
MAX_ADDRESS_CHARS = 254
MAX_MESSAGE_ID_CHARS = 250
TIMEOUT = 30.0

#: How the email is written for the wire: CRLF line ends, and 7-bit only -
#: accented letters and emoji in the text are encoded (quoted-printable or
#: base64), so the email arrives intact even through a server that does not
#: take 8-bit mail. What the recipient reads is the text on the card.
SMTP_POLICY = _SMTP.clone(cte_type="7bit")

TLS_MODES = ("ssl", "starttls", "off")
_DEFAULT_PORT = {"ssl": 465, "starttls": 587, "off": 25}

#: The words a card and the Settings line use for each way of travelling.
TLS_WORDS = {
    "ssl": "encrypted from the start (SSL/TLS)",
    "starttls": "encrypted before logging in (STARTTLS - if the server will not encrypt, "
                "nothing is sent)",
    "off": "NOT encrypted (allowed only because the server is on this PC or your own "
           "network)",
}

#: What saying no costs. Always on the card.
IF_REFUSED = "nothing is sent, and Jarvis tells you it was not sent."

#: What the result says when a send may or may not have gone through.
MAYBE_SENT = ("The mail server stopped answering after the email was handed over, so "
              "Jarvis cannot tell whether it was sent. Check your Sent folder before "
              "asking again - Jarvis never retries, so it cannot go twice by itself.")


# --------------------------------------------------------------------------
#   Settings - read fresh every call
# --------------------------------------------------------------------------

_HOST_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
                      r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$")
_IPV6_RE = re.compile(r"^[0-9A-Fa-f:.]{2,45}$")

#: An address: the dot-atom local part and a host name with at least one dot.
_LOCAL = r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*"
_DOMAIN = (r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
           r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+")
_ADDRESS_RE = re.compile(rf"^{_LOCAL}@{_DOMAIN}$")

#: <left@right>, printable ASCII, no spaces or angle brackets inside.
_MESSAGE_ID_RE = re.compile(r"^<[\x21-\x3b\x3d\x3f-\x7e]+@[\x21-\x3b\x3d\x3f-\x7e]+>$")


def valid_address(value) -> bool:
    """A plain email address, ASCII, at most MAX_ADDRESS_CHARS - no display
    name, no comment, no second address, nothing that could start a new
    header line."""
    return (isinstance(value, str) and 3 <= len(value) <= MAX_ADDRESS_CHARS
            and _ADDRESS_RE.match(value) is not None)


def _host_ok(host: str) -> bool:
    if not host or len(host) > 253:
        return False
    if ":" in host:
        return _IPV6_RE.match(host) is not None
    return _HOST_RE.match(host) is not None


def _guess_smtp_host(imap_host: str) -> str:
    """imap.gmail.com -> smtp.gmail.com; "imap.X" -> "smtp.X"; else ""."""
    h = (imap_host or "").strip().lower().rstrip(".")
    if h.startswith("imap.") and _host_ok(h):
        return "smtp." + h[len("imap."):]
    return ""


def _own_network(host: str, port: int) -> bool:
    """This PC or one of the owner's own networks - jarvis_local_http's rule,
    asked through its public check with an address shaped for it."""
    try:
        import jarvis_local_http
    except Exception:
        return False
    shown = f"[{host}]" if ":" in host else host
    return jarvis_local_http.plain_http_problem(
        f"http://{shown}:{port}/", SMTP_HOST_ENV, "your mail password") == ""


@dataclass(frozen=True)
class Settings:
    sender: str = ""
    host: str = ""
    port: int = 465
    tls: str = "ssl"
    host_guessed: bool = False
    problem: str = ""           # "" when sending is set up

    @property
    def ready(self) -> bool:
        return not self.problem


def settings() -> Settings:
    """How an email would leave, from the environment. Never the password -
    only whether one is set. Opens nothing."""
    sender = os.environ.get(USER_ENV, "").strip()
    has_password = bool(os.environ.get(PASSWORD_ENV, ""))
    host = os.environ.get(SMTP_HOST_ENV, "").strip().lower().rstrip(".")
    guessed = False
    if not host:
        host = _guess_smtp_host(os.environ.get(IMAP_HOST_ENV, ""))
        guessed = bool(host)
    tls = os.environ.get(SMTP_TLS_ENV, "").strip().lower()
    raw_port = os.environ.get(SMTP_PORT_ENV, "").strip()
    port = None
    port_problem = ""
    if raw_port:
        try:
            port = int(raw_port)
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            port_problem = f"{SMTP_PORT_ENV} is not a port number"
            port = None
    if tls and tls not in TLS_MODES:
        return Settings(sender, host, port or 465, "ssl", guessed,
                        f"{SMTP_TLS_ENV} must be ssl, starttls or off")
    if not tls:
        tls = "ssl" if port in (None, 465) else "starttls"
    port = port or _DEFAULT_PORT[tls]

    def s(problem: str) -> Settings:
        return Settings(sender, host, port, tls, guessed, problem)

    if not sender:
        return s(f"{USER_ENV} is not set - sending uses the same account as reading "
                 f"email, and there is none")
    if not valid_address(sender):
        return s(f"{USER_ENV} is not an email address, so Jarvis cannot tell which "
                 f"address to send from")
    if not has_password:
        return s(f"{PASSWORD_ENV} is not set, so the mail server would refuse the login")
    if port_problem:
        return s(port_problem)
    if not host:
        return s(f"{SMTP_HOST_ENV} is not set, and the sending server cannot be worked "
                 f"out from {IMAP_HOST_ENV} (it does not start with \"imap.\")")
    if not _host_ok(host):
        return s(f"{SMTP_HOST_ENV} is not a plain server name or address")
    if tls == "off" and not _own_network(host, port):
        return s(f"{SMTP_TLS_ENV} is off, and {host} is not this PC or one of your own "
                 f"networks, so your password and the email would cross the internet "
                 f"unencrypted, where anyone along the way could read them. Nothing is "
                 f"sent that way. Unencrypted sending is allowed only to this PC, your "
                 f"home network, Tailscale or NordVPN Meshnet; use ssl or starttls")
    return s("")


# --------------------------------------------------------------------------
#   The plan - worked out locally, sent by no one yet
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
    tls: str
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
                "tls": self.tls, "problem": self.problem}


def fingerprint(p: Plan) -> str:
    """A fingerprint of everything that would be sent and where. Taken when
    the plan is made; run() takes it again and sends nothing if it differs."""
    parts = [p.sender, "\x1f".join(p.to), "\x1f".join(p.cc), p.subject, p.body,
             p.in_reply_to, p.host, str(p.port), p.tls]
    return hashlib.sha256("\x1e".join(parts).encode("utf-8")).hexdigest()


def _as_list(value, name: str):
    """A list of strings from what the model sent; (list, problem)."""
    if value is None or value == "":
        return [], ""
    if isinstance(value, str):
        # One address as a plain string is accepted; a comma-separated
        # string is not split, so "a@x.com, b@y.com" is refused as one bad
        # address rather than guessed at.
        return [value], ""
    if not isinstance(value, (list, tuple)):
        return [], f"{name} must be a list of email addresses"
    if not all(isinstance(v, str) for v in value):
        return [], f"{name} must be a list of email addresses"
    return list(value), ""


#: Control characters and the invisible "format" characters (right-to-left
#: overrides, zero-width joiners) that can make a card read differently
#: from what is sent. A line break and a tab are allowed in the body.
_INVISIBLE = ("Cc", "Cf", "Cs", "Co", "Cn")


def _hidden_chars(text: str, allow: str = "") -> bool:
    return any(unicodedata.category(ch) in _INVISIBLE and ch not in allow for ch in text)


def plan(to, cc=None, subject: str = "", body: str = "",
         reply_to_message_id: Optional[str] = None) -> Plan:
    """Work out the one email this would send. Opens no socket. A plan with
    a `problem` is never sent and needs no card: the problem says why."""
    st = settings()

    def refused(problem: str) -> Plan:
        p = Plan(sender=st.sender, to=(), cc=(), subject="", body="", in_reply_to="",
                 host=st.host, port=st.port, tls=st.tls, problem=problem)
        return replace(p, digest=fingerprint(p))

    to_list, why = _as_list(to, "to")
    if why:
        return refused(why)
    cc_list, why = _as_list(cc, "cc")
    if why:
        return refused(why)
    to_list = [a.strip() for a in to_list]
    cc_list = [a.strip() for a in cc_list]
    if not to_list:
        return refused("there is nobody to send it to - `to` needs at least one address")
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
        return refused(f"that is {len(seen)} people; one email may go to at most "
                       f"{MAX_RECIPIENTS} (To and Cc together)")

    if not isinstance(subject, str):
        return refused("the subject must be text")
    subject = subject.strip()
    if not subject:
        return refused("the email has no subject")
    if len(subject) > MAX_SUBJECT_CHARS:
        return refused(f"the subject is {len(subject)} characters; at most "
                       f"{MAX_SUBJECT_CHARS}")
    if _hidden_chars(subject):
        return refused("the subject holds a line break or an invisible character, which "
                       "would make the card read differently from what is sent")

    if not isinstance(body, str):
        return refused("the email's text must be text")
    body = body.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    if not body.strip():
        return refused("the email has no text")
    if len(body) > MAX_BODY_CHARS:
        return refused(f"the email is {len(body)} characters; one approval card can show "
                       f"at most {MAX_BODY_CHARS} in full, and a card never shows less "
                       f"than everything it sends. Write it shorter, or the owner can "
                       f"send it from their own mail app")
    if _hidden_chars(body, allow="\n\t"):
        return refused("the email's text holds invisible or control characters, which "
                       "would make the card read differently from what is sent")

    in_reply_to = ""
    if reply_to_message_id not in (None, ""):
        mid = str(reply_to_message_id).strip()
        if not mid.startswith("<"):
            mid = f"<{mid}>"
        if len(mid) > MAX_MESSAGE_ID_CHARS or not _MESSAGE_ID_RE.match(mid):
            return refused("reply_to_message_id is not a message id (like <abc@mail.example.com>)")
        in_reply_to = mid

    p = Plan(sender=st.sender, to=tuple(dedup_to), cc=tuple(dedup_cc), subject=subject,
             body=body, in_reply_to=in_reply_to, host=st.host, port=st.port, tls=st.tls,
             problem=st.problem and f"sending email is not set up on this PC: {st.problem}")
    return replace(p, digest=fingerprint(p))


def describe(p: Plan) -> str:
    """The card text: every recipient, the subject and the WHOLE email, word
    for word - never a summary - then how it travels and what no costs."""
    if not p.ready:
        return (f"Jarvis would like to send an email, but {p.problem}. "
                f"Nothing would be sent.")
    lines = [
        "Send this email from your account? It goes only if you approve, exactly as "
        "shown - every word is below.",
        "",
        f"From: {p.sender}",
        f"To: {', '.join(p.to)}",
        f"Cc: {', '.join(p.cc) if p.cc else '(nobody)'}",
        f"Subject: {p.subject}",
    ]
    if p.in_reply_to:
        lines.append(f"In reply to: {p.in_reply_to}")
    lines += [
        "",
        "---------- the whole email ----------",
        p.body,
        "---------- end of the email ----------",
        "",
        "No attachments, no hidden (Bcc) recipients.",
        f"It goes through {p.host}, port {p.port}, {TLS_WORDS[p.tls]}. Jarvis logs in "
        f"there as {p.sender}; your password goes to that server and nowhere else.",
        "Once sent, an email cannot be taken back.",
        "",
        f"If you say no: {IF_REFUSED}",
    ]
    return "\n".join(lines)


def message(p: Plan) -> EmailMessage:
    """The email itself, built only from the plan: the From, To, Cc,
    Subject and text the card shows, plus the date, a message id and - for a
    reply - the two threading headers. Nothing else."""
    msg = EmailMessage(policy=SMTP_POLICY)
    msg["From"] = p.sender
    msg["To"] = ", ".join(p.to)
    if p.cc:
        msg["Cc"] = ", ".join(p.cc)
    msg["Subject"] = p.subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=p.sender.rsplit("@", 1)[-1])
    if p.in_reply_to:
        msg["In-Reply-To"] = p.in_reply_to
        msg["References"] = p.in_reply_to
    msg.set_content(p.body + "\n")
    return msg


# --------------------------------------------------------------------------
#   Whether the owner's settings let an email go at all
# --------------------------------------------------------------------------

def tier_of(action: str) -> str:
    try:
        import jarvis_framework as fw
        return str(fw.action_tier(action))
    except Exception as exc:
        return f"unreadable ({type(exc).__name__})"


def tier_problem(tier_of: Callable[[str], str] = tier_of) -> str:
    """"" when an email can be asked about, else why not, in plain words.
    Sending acts only on tier "ask": "auto" or "notify" would send with
    nobody asked, and a card that could not end in a person deciding is
    never raised."""
    tier = tier_of(ACTION)
    if tier != "ask":
        if tier == "never":
            return (f"sending email is switched off on this PC ({ACTION} is \"never\" in "
                    f"jarvis-framework.toml's [autonomy.tiers])")
        return (f"{ACTION} is tier {tier!r} in jarvis-framework.toml, which would send "
                f"without asking anyone; every email needs the owner's yes on a card, so "
                f"nothing is sent until it is \"ask\"")
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
    """What the Settings line in both apps shows: whether sending is set up,
    from which address, through which server - never the password, only
    whether one is set. `said` is the one line both apps print as it is."""
    st = settings()
    on = TOOL in (tools_enabled or _tools_enabled)()
    tier_why = tier_problem(tier_of)
    route = (f"from {st.sender} through {st.host}, port {st.port}, "
             f"{'encrypted' if st.tls != 'off' else 'not encrypted (your own network)'}")
    if st.problem:
        state = "not_set_up"
        said = (f"Not set up: {st.problem}. The steps are in backend/README.md, "
                f"\"Sending email\".")
    elif tier_why:
        state = "off" if tier_of(ACTION) == "never" else "refused"
        said = f"Set up ({route}), but {tier_why}."
    elif not on:
        state = "tool_off"
        said = (f"Set up ({route}). Jarvis does not offer to send until \"{TOOL}\" is "
                f"added to [tools].enabled in jarvis-framework.toml on the PC.")
    else:
        state = "ready"
        said = (f"Ready: {route}. Every email is its own approval card showing all of "
                f"it; there is no \"always allow\".")
    return {
        "available": True,
        "state": state,
        "ready": state == "ready",
        "from": st.sender if valid_address(st.sender) else "",
        "server": st.host,
        "port": st.port,
        "encryption": st.tls,
        "server_guessed": st.host_guessed,
        "password_set": bool(os.environ.get(PASSWORD_ENV, "")),
        "tool_enabled": on,
        "said": said,
        "limits": {"recipients": MAX_RECIPIENTS, "subject_chars": MAX_SUBJECT_CHARS,
                   "body_chars": MAX_BODY_CHARS, "attachments": False},
    }


def handle_get() -> tuple:
    """GET /api/email/sending (email-send.patch)."""
    return 200, view()


# --------------------------------------------------------------------------
#   Sending - one connection, one email, never a retry
# --------------------------------------------------------------------------

#: Builds the TLS context. Only a test replaces it (to trust its own
#: stand-in server's certificate); the default checks the certificate and
#: the name against the system's trusted authorities.
_SSL_CONTEXT = ssl.create_default_context


class _Refused(Exception):
    """A reason of ours, in plain words, that nothing was sent."""


def _register_with_scrubber(user: str, password: str) -> None:
    """The password's value is already hidden in logs by its variable name
    (jarvis_scrub). SMTP login sends it base64-encoded, so those forms are
    registered too - belt and braces, since nothing here prints them."""
    try:
        import jarvis_scrub
    except Exception:
        return
    forms = [password,
             base64.b64encode(password.encode("utf-8")).decode("ascii"),
             base64.b64encode(f"\0{user}\0{password}".encode("utf-8")).decode("ascii")]
    for f in forms:
        try:
            jarvis_scrub.register_secret(f)
        except Exception:
            pass


def _smtp_send(p: Plan, data: bytes, password: str, phase: list) -> dict:
    """The real conversation. `phase` is updated as it goes, so a failure can
    say whether the email may have left. smtplib's debug output stays off.
    Returns sendmail's dict of refused recipients (empty when all took it)."""
    ctx = _SSL_CONTEXT()
    phase[0] = "connect"
    if p.tls == "ssl":
        conn = smtplib.SMTP_SSL(p.host, p.port, local_hostname="localhost",
                                timeout=TIMEOUT, context=ctx)
    else:
        conn = smtplib.SMTP(p.host, p.port, local_hostname="localhost", timeout=TIMEOUT)
    conn.set_debuglevel(0)
    try:
        conn.ehlo()
        if p.tls == "starttls":
            phase[0] = "tls"
            if not conn.has_extn("starttls"):
                raise _Refused("the mail server did not offer to encrypt the connection "
                               "(STARTTLS), so Jarvis did not log in or send anything")
            conn.starttls(context=ctx)
            conn.ehlo()
        elif p.tls == "off" and not _own_network(p.host, p.port):
            raise _Refused("unencrypted sending is allowed only inside your own networks")
        phase[0] = "login"
        conn.login(p.sender, password)
        phase[0] = "send"
        return conn.sendmail(p.sender, list(p.recipients), data)
    finally:
        try:
            conn.quit()
        except Exception:
            try:
                conn.close()
            except Exception:
                pass


#: The plain sentence for each way sending can fail. The exception's own
#: message is never used: it can quote the server's reply.
def _failure(exc: BaseException, phase: str) -> dict:
    name = type(exc).__name__
    if isinstance(exc, _Refused):
        return {"ok": False, "sent": False, "error": f"not sent: {exc}."}
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        words = ("the mail server refused the login. For Gmail, check the app "
                 "password in JARVIS_IMAP_PASSWORD")
    elif isinstance(exc, smtplib.SMTPRecipientsRefused):
        words = "the mail server refused every recipient"
    elif isinstance(exc, smtplib.SMTPSenderRefused):
        words = "the mail server refused to send from this address"
    elif isinstance(exc, smtplib.SMTPNotSupportedError):
        words = "the mail server does not support what Jarvis needs (encryption or login)"
    elif isinstance(exc, ssl.SSLCertVerificationError):
        words = ("the mail server's certificate could not be checked, so Jarvis did not "
                 "log in or send anything")
    elif isinstance(exc, (TimeoutError, OSError)) and phase in ("connect", "tls"):
        words = "the mail server could not be reached"
    elif isinstance(exc, smtplib.SMTPResponseException):
        words = "the mail server refused the email"
    else:
        words = f"sending failed ({name})"
    # Once the email is being handed over, only an ANSWER from the server
    # (a refusal) proves it did not go. A dropped connection or a timeout
    # there proves nothing either way - so it is said so, and never retried.
    if phase == "send" and not isinstance(exc, (smtplib.SMTPRecipientsRefused,
                                                smtplib.SMTPResponseException)):
        return {"ok": False, "sent": "unknown", "error": f"{MAYBE_SENT} ({name})"}
    return {"ok": False, "sent": False, "error": f"not sent: {words} ({name})."}


def _audit(event: str, detail: dict) -> None:
    """Counts only - never an address, a subject or a word of the text."""
    try:
        import jarvis_framework as fw
        fw.audit_log(event, detail)
    except Exception:
        pass


def run(p: Plan, *, approved: bool = False,
        send: Optional[Callable[[Plan, bytes, str, list], dict]] = None) -> dict:
    """Send an approved plan - exactly it, once. `approved` has no default
    of True. `send` is injectable for tests; the default is `_smtp_send`.

    Refused, with nothing sent, when: not approved; the plan has a problem;
    its fingerprint no longer matches (its content changed after the card
    was made); the account, server or encryption in the settings is no
    longer what the card showed; or the password is gone."""
    if not approved:
        return {"ok": False, "sent": False, "error": "not approved; nothing was sent"}
    if not p.ready:
        return {"ok": False, "sent": False, "error": f"not sent: {p.problem}."}
    if not p.digest or fingerprint(p) != p.digest:
        return {"ok": False, "sent": False,
                "error": "not sent: the email changed after the card was made, so it is "
                         "not the one that was approved. Nothing was sent."}
    now = settings()
    if (now.problem or now.sender != p.sender or now.host != p.host or now.port != p.port
            or now.tls != p.tls):
        return {"ok": False, "sent": False,
                "error": "not sent: the account or the mail server settings changed after "
                         "the card was shown, so this is not what was approved. Nothing "
                         "was sent."}
    password = os.environ.get(PASSWORD_ENV, "")
    if not password:
        return {"ok": False, "sent": False, "error": f"not sent: {PASSWORD_ENV} is not set."}
    _register_with_scrubber(p.sender, password)
    data = message(p).as_bytes(policy=SMTP_POLICY)
    phase = ["start"]
    try:
        refused = (send or _smtp_send)(p, data, password, phase) or {}
    except Exception as exc:
        out = _failure(exc, phase[0])
        _audit("email_send_failed", {"recipients": len(p.recipients), "phase": phase[0],
                                     "error": type(exc).__name__,
                                     "sent": out.get("sent")})
        return out
    refused_list = sorted(str(a) for a in dict(refused))
    took = [a for a in p.recipients if a not in refused_list]
    _audit("email_sent", {"recipients": len(took), "refused": len(refused_list),
                          "chars": len(p.body)})
    said = f"Sent to {', '.join(took)}."
    if refused_list:
        said += f" The mail server refused {', '.join(refused_list)}, so they did not get it."
    return {"ok": True, "sent": True, "to": list(p.to), "cc": list(p.cc),
            "refused": refused_list, "said": said}
